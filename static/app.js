let eventSources = {}       // room_id -> EventSource
const currentRooms = {}     // room_id -> {nickname}
const mysteries = {}        // sec_uid -> {display, real_name, ..., room_id, room_nickname}
let disconnectTimers = {}   // room_id -> timer
let recordAllEnabled = false  // 是否记录全部用户
let currentView = 'mystery'   // 'mystery' 或 'all'
let lastRoomId = null         // 最近监听的房间，用于按钮切换停止
let historyCache = []          // 搜索历史缓存（预加载零延迟）

function escapeHtml(text) {
  const d = document.createElement('div')
  d.textContent = text
  return d.innerHTML
}

function setStatus(text, color) {
  document.getElementById('statusText').textContent = text
  document.getElementById('dot').className = 'dot ' + color
}

function showAnonymousBanner(msg) {
  const b = document.getElementById('anonymousBanner')
  document.getElementById('anonymousMsg').innerHTML = msg
  b.classList.add('show')
}

function resetBtnText() {
  const btn = document.getElementById('btn')
  const rooms = Object.keys(currentRooms)
  const input = document.getElementById('input').value.trim()
  if (rooms.length > 0 && !input) {
    btn.textContent = '停止'
    btn.className = 'stop-btn'
  } else {
    btn.textContent = '🔍 监听'
    btn.className = ''
  }
}

function connect() {
  const input = document.getElementById('input').value.trim()
  if (!input) return
  const btn = document.getElementById('btn')
  btn.disabled = true
  btn.textContent = '解析中...'
  setStatus('解析中...', 'gray')

  fetch('/api/resolve', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({input: input})
  })
  .then(r => r.json())
  .then(data => {
    if (!data.success) {
      showToast('❌ ' + data.error)
      btn.disabled = false
      resetBtnText()
      return
    }
    if (data.room_id && (data.live_status == 1 || data.live_status === undefined)) {
      if (currentRooms[data.room_id]) {
        showToast('⚠️ 已在监听该直播间')
        btn.disabled = false
        resetBtnText()
        return
      }
      startListening(data.room_id, data.nickname || '')
      // 保存搜索历史
      const saveInput = input
      const saveNickname = data.nickname || ''
      const saveRoomId = data.room_id
      fetch('/api/search_history/save', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({input: saveInput, nickname: saveNickname, room_id: saveRoomId})
      }).then(r => r.json()).then(res => {
        if (res.success) {
          // 本地缓存同步更新
          historyCache = historyCache.filter(item => item.input_text !== saveInput)
          historyCache.unshift({input_text: saveInput, nickname: saveNickname, room_id: saveRoomId, created_at: Math.floor(Date.now()/1000)})
          if (historyCache.length > 20) historyCache = historyCache.slice(0, 20)
        }
      }).catch(() => {})
    } else if (data.room_id && data.live_status == 0) {
      showToast('❌ 该主播未在直播')
      btn.disabled = false
      resetBtnText()
    } else {
      showToast('❌ 无法获取直播间信息')
      btn.disabled = false
      resetBtnText()
    }
  })
  .catch(err => {
    showToast('❌ 网络错误: ' + err.message)
    btn.disabled = false
    resetBtnText()
  })
}

// ========== 搜索历史 ==========

function loadRoomHistory() {
  const dd = document.getElementById('historyDropdown')
  renderHistoryFromCache()
  // 后台刷新缓存，供下一次 focus
  refreshHistoryCache()
}

function renderHistoryFromCache() {
  const dd = document.getElementById('historyDropdown')
  if (!historyCache || historyCache.length === 0) {
    dd.innerHTML = '<div class="empty-msg">暂无搜索记录</div>'
    dd.style.display = 'block'
    return
  }
  let html = ''
  historyCache.forEach(item => {
    const name = escapeHtml(item.nickname || item.input_text)
    html += `<div class="item" onclick="selectHistory('${escapeHtml(item.input_text)}', '${escapeHtml(item.nickname || '')}' )">`
    html += `<span class="name">🎙 ${name}</span>`
    html += `<button class="del-btn" onclick="event.stopPropagation();removeRoomHistory('${escapeHtml(item.input_text)}')">✕</button>`
    html += `</div>`
  })
  dd.innerHTML = html
  dd.style.display = 'block'
}

function refreshHistoryCache() {
  fetch('/api/search_history/list')
    .then(r => r.json())
    .then(res => {
      if (res.success && res.data) historyCache = res.data
    })
    .catch(() => {})
}

function removeRoomHistory(input) {
  // 本地同步删除
  historyCache = historyCache.filter(item => item.input_text !== input)
  renderHistoryFromCache()
  // 服务端异步删除
  fetch('/api/search_history/delete', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({input: input})
  })
  .then(r => r.json())
  .catch(() => {})
}

function selectHistory(input, nickname) {
  document.getElementById('input').value = input
  document.getElementById('historyDropdown').style.display = 'none'
  connect()
}

function handleBtnClick() {
  const btn = document.getElementById('btn')
  const rooms = Object.keys(currentRooms)
  // 有输入内容 → 监听模式
  const input = document.getElementById('input').value.trim()
  if (input) {
    connect()
    return
  }
  // 无输入内容 + 有房间 → 停止模式
  if (rooms.length === 1) {
    stopRoom(rooms[0])
    btn.textContent = '🔍 监听'
    btn.className = ''
    lastRoomId = null
  } else if (rooms.length > 1) {
    showStopDialog()
  }
}

function showStopDialog() {
  const rooms = Object.keys(currentRooms)
  const roomColors = ['#fe2c55', '#5ac8fa', '#34c759']
  let html = '<div class="stop-overlay" id="stopOverlay" onclick="closeStopDialog(event)"><div class="stop-box" onclick="event.stopPropagation()">'
  html += '<h3>选择要停止的房间</h3>'
  rooms.forEach((rid, i) => {
    const nick = currentRooms[rid]?.nickname || rid.slice(0,10)
    html += `<div class="stop-item" onclick="stopRoomAndClose('${rid}')"><span class="stop-dot" style="background:${roomColors[i%3]}"></span>${escapeHtml(nick)}<span style="margin-left:auto;color:#fe2c55;font-weight:600">停止</span></div>`
  })
  html += '<div class="stop-all-item" onclick="stopAllAndClose()">全部停止</div>'
  html += '<div class="stop-cancel" onclick="closeStopDialog()">取消</div>'
  html += '</div></div>'
  document.body.insertAdjacentHTML('beforeend', html)
}

function closeStopDialog(e) {
  const el = document.getElementById('stopOverlay')
  if (el) el.remove()
}

function stopRoomAndClose(roomId) {
  closeStopDialog()
  stopRoom(roomId)
  const rooms = Object.keys(currentRooms)
  const btn = document.getElementById('btn')
  if (rooms.length === 0) {
    btn.textContent = '🔍 监听'
    btn.className = ''
    lastRoomId = null
  }
}

function stopAllAndClose() {
  closeStopDialog()
  stopAll()
  const btn = document.getElementById('btn')
  btn.textContent = '🔍 监听'
  btn.className = ''
  lastRoomId = null
}

function toggleRecordAll() {
  // 已废弃，由 switchMode 替代
}
function switchView(view) {
  // 已废弃，由 switchMode 替代
}

function switchMode(mode) {
  const allBtn = document.getElementById('modeAll')
  const hisBtn = document.getElementById('modeHistory')
  const feedBtn = document.getElementById('modeFeed')
  // 已在全部/历史/公屏模式下再次点击 → 刷新
  if (mode === 'all' && currentView === 'all') {
    renderAllRecords()
    return
  }
  if (mode === 'history' && currentView === 'history') {
    renderHistory()
    return
  }
  if (mode === 'feed' && currentView === 'feed') {
    loadFeed()
    return
  }
  currentView = mode
  const isAll = mode === 'all'
  const isHis = mode === 'history'
  const isFeed = mode === 'feed'
  // 更新按钮状态
  document.getElementById('modeMystery').className = 'mode-btn' + (mode === 'mystery' ? ' active' : '')
  allBtn.className = 'mode-btn' + (isAll ? ' active' : '')
  hisBtn.className = 'mode-btn' + (isHis ? ' active' : '')
  if (feedBtn) feedBtn.className = 'mode-btn' + (isFeed ? ' active' : '')
  allBtn.textContent = isAll ? '刷新' : '📋全部'
  hisBtn.textContent = isHis ? '刷新' : '📜历史'
  // 切换容器显示
  const eventsEl = document.getElementById('events')
  const feedEl = document.getElementById('feedContainer')
  if (isFeed) {
    eventsEl.style.display = 'none'
    if (feedEl) feedEl.style.display = ''
    loadFeed()
    return
  } else {
    eventsEl.style.display = ''
    if (feedEl) feedEl.style.display = 'none'
  }
  // 通知后端：全部用户模式才开启录制
  if (isAll) {
    fetch('/api/toggle_record_all', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({enabled: true})
    })
  }
  if (isHis) {
    renderHistory()
  } else if (isAll) {
    renderAllRecords()
  } else {
    renderMysteries()
  }
}

function showToast(msg) {
  const el = document.getElementById('events')
  // 只在没有任何神秘人时显示toast
  if (Object.keys(mysteries).length === 0) {
    el.innerHTML = `<div class="empty" style="color:#fe2c55">${msg}</div>`
  }
}

function startListening(roomId, nickname) {
  fetch('/api/start', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({room_id: roomId, nickname: nickname})
  })
  .then(r => r.json())
  .then(data => {
    if (data.success) {
      currentRooms[roomId] = {nickname: nickname || roomId}
      lastRoomId = roomId
      document.getElementById('btn').textContent = '停止'
      document.getElementById('btn').className = 'stop-btn'
      // 首次监听显示提示
      if (Object.keys(mysteries).length === 0) {
        document.getElementById('events').innerHTML = '<div class="empty"><div class="icon">🎯</div>等待神秘人出现...</div>'
      }
      setStatus('监听中', 'green')
      document.getElementById('btn').disabled = false
      document.getElementById('input').value = ''
      resetBtnText()
      connectSSE(roomId)
    } else {
      showToast('❌ ' + (data.error || '启动失败'))
      document.getElementById('btn').disabled = false
      document.getElementById('btn').textContent = '🔍 监听'
    }
  })
}

function connectSSE(roomId) {
  // 先拉取已有历史
  fetch('/api/history/' + roomId)
    .then(r => r.json())
    .then(data => {
      if (data.success && data.history && data.history.length > 0) {
        data.history.forEach(h => {
          if (!mysteries[mKey(h)]) {
            const realName = h.real_name || h.display
            const extraData = h.extra || null
            mysteries[mKey(h)] = {
              display: h.display, real_name: realName,
              sec_uid: h.sec_uid,
              unique_id: h.unique_id || extraData?.unique_id || '',
              badge_level: h.badge_level || 0, consume_level: h.consume_level || 0,
              extra: extraData,
              room_id: h.room_id || roomId,
              room_nickname: h.room_nickname || currentRooms[roomId]?.nickname || roomId,
              enter_count: 1,
              chats: [], gifts: [],
              time: Date.now(), expanded: false,
              is_regular: h.is_regular || false
            }
          }
        })
        if (currentView !== 'all') renderMysteries()
      }
    })

  const es = new EventSource('/stream/' + roomId)
  eventSources[roomId] = es
  disconnectTimers[roomId] = null

  es.onmessage = function(e) {
    if (!e.data) return
    // 收到消息取消该房间的断线延时
    cancelDisconnect(roomId)
    try {
      const event = JSON.parse(e.data)
      handleEvent(event, roomId)
    } catch(err) { console.warn('[SSE] parse/handle error:', err) }
  }
  es.onerror = function() {
    if (disconnectTimers[roomId]) return
    disconnectTimers[roomId] = setTimeout(() => {
      setStatus('已断开', 'red')
      disconnectTimers[roomId] = null
    }, 5000)
  }
}

function cancelDisconnect(roomId) {
  if (disconnectTimers[roomId]) {
    clearTimeout(disconnectTimers[roomId])
    disconnectTimers[roomId] = null
  }
}

function mKey(d) {
  const isPrivate = !d.sec_uid && (!d.unique_id || d.unique_id === '?')
  return d.room_id + ':' + (isPrivate
    ? d.display + ':' + (d.consume_level||0) + ':' + (d.badge_level||0)
    : d.sec_uid || d.display || '?')
}

function handleEvent(event, roomId) {
  const d = event.data
  // 补充房间信息
  const roomNick = currentRooms[roomId]?.nickname || roomId
  switch(event.type) {
    case 'init':
    case 'connected':
      cancelDisconnect(roomId)
      setStatus('监听中', 'green')
      // 匿名模式提示
      if (d.is_anonymous) {
        showAnonymousBanner(d.is_anonymous_msg || '当前为匿名模式直播间，仅能通过<b>礼物</b>获取用户真实身份。<br>识别到的用户请点击上方 <b>「📋全部」</b> 按钮查看，不会存入「📜历史」。')
      }
      break
    case 'room_anonymous':
      showAnonymousBanner(d.message || '当前为匿名模式直播间，仅能通过礼物获取用户真实身份。')
      break
    case 'disconnected':
      if (d.reconnecting) {
        setStatus('重连中...', 'gray')
      } else {
        setStatus('已断开', 'red')
      }
      break
    case 'mystery_enter':
      if (mysteries[mKey(d)]) {
        // 同一个人换马甲了
        const old = mysteries[mKey(d)]
        if (old.display && old.display !== d.display) {
          if (!old.aliases) old.aliases = []
          if (!old.aliases.includes(old.display)) old.aliases.push(old.display)
          if (!old.aliases.includes(d.display)) old.aliases.push(d.display)
        }
        old.display = d.display
        old.real_name = d.real_name
        old.sec_uid = d.sec_uid
        old.unique_id = d.unique_id || d.extra?.unique_id || old.unique_id
        old.badge_level = d.badge_level || old.badge_level
        old.consume_level = d.consume_level || old.consume_level
        old.extra = d.extra || old.extra
        old.room_id = d.room_id || old.room_id
        old.room_nickname = d.room_nickname || old.room_nickname
        old.enter_count = (old.enter_count || 0) + 1
        old.time = Date.now()
      } else {
        mysteries[mKey(d)] = {
          display: d.display, real_name: d.real_name,
          sec_uid: d.sec_uid,
          unique_id: d.unique_id || d.extra?.unique_id || '',
          badge_level: d.badge_level || 0, consume_level: d.consume_level || 0,
          extra: d.extra || null,
          room_id: d.room_id || roomId,
          room_nickname: d.room_nickname || roomNick,
          enter_count: 1,
          chats: [], gifts: [], aliases: [],
          time: Date.now(), expanded: false,
          is_regular: d.is_regular || false
        }
      }
      // 调试：公屏事件计数器
      document.title = '📡' + new Date().toLocaleTimeString() + ' ' + (d.display || '?').slice(0,12) + ' | 神秘人猎人'
      if (currentView !== 'all' && !d.is_regular) renderSingleCard(mKey(d))
      if (currentView === 'feed') appendFeedItem(event)
      break
    case 'mystery_chat':
      if (!mysteries[mKey(d)]) {
        mysteries[mKey(d)] = {
          display: d.display, real_name: d.real_name,
          sec_uid: d.sec_uid, unique_id: d.unique_id || '',
          badge_level: d.badge_level || 0, consume_level: d.consume_level || 0,
          extra: null, chats: [], gifts: [], aliases: [],
          time: Date.now(), expanded: false,
          room_id: d.room_id || roomId,
          room_nickname: d.room_nickname || roomNick,
          enter_count: 0, is_regular: d.is_regular || false
        }
      } else {
        if (d.display && d.display !== mysteries[mKey(d)].display) {
          if (!mysteries[mKey(d)].aliases) mysteries[mKey(d)].aliases = []
          if (!mysteries[mKey(d)].aliases.includes(d.display)) mysteries[mKey(d)].aliases.push(d.display)
        }
      }
      mysteries[mKey(d)].chats.push({content: d.content, time: Date.now()})
      document.title = '💬' + new Date().toLocaleTimeString() + ' ' + (d.display || '?').slice(0,12) + ' | 神秘人猎人'
      if (currentView !== 'all' && !d.is_regular) renderSingleCard(mKey(d))
      if (currentView === 'feed') appendFeedItem(event)
      break
    case 'mystery_gift':
      if (!mysteries[mKey(d)]) {
        mysteries[mKey(d)] = {
          display: d.display, real_name: d.real_name,
          sec_uid: d.sec_uid, unique_id: '',
          badge_level: d.badge_level || 0, consume_level: d.consume_level || 0,
          extra: null, chats: [], gifts: [], aliases: [],
          time: Date.now(), expanded: false,
          room_id: d.room_id || roomId,
          room_nickname: d.room_nickname || roomNick,
          enter_count: 0, is_regular: d.is_regular || false
        }
      } else {
        // 同一个人换马甲（送礼时发现不同马甲）
        if (d.display && d.display !== mysteries[mKey(d)].display) {
          if (!mysteries[mKey(d)].aliases) mysteries[mKey(d)].aliases = []
          if (!mysteries[mKey(d)].aliases.includes(d.display)) mysteries[mKey(d)].aliases.push(d.display)
        }
        if (d.real_name && d.real_name !== d.display) {
          mysteries[mKey(d)].real_name = d.real_name
          if (d.extra) mysteries[mKey(d)].extra = d.extra
        }
      }
      mysteries[mKey(d)].gifts.push({name: d.gift_name, count: d.count, time: Date.now()})
      document.title = '🎁' + new Date().toLocaleTimeString() + ' ' + (d.display || '?').slice(0,12) + ' | 神秘人猎人'
      if (currentView !== 'all' && !d.is_regular) renderSingleCard(mKey(d))
      if (currentView === 'feed') appendFeedItem(event)
      break
    case 'room_offline':
      setStatus('已断开', 'red')
      // 直播间已下播，自动停止监听
      showToast('📴 直播已结束，已自动停止')
      stopRoom(roomId)
      break
    case 'error':
      break
  }
}

function renderMysteries() {
  const container = document.getElementById('events')
  // 过滤：仅显示神秘人 / 显示全部
  const mysteryOnly = currentView === 'mystery'
  const keys = Object.keys(mysteries)
  const filtered = mysteryOnly ? keys.filter(k => !mysteries[k].is_regular) : keys
  if (filtered.length === 0) {
    container.innerHTML = '<div class="empty"><div class="icon">🎯</div>暂无数据</div>'
    return
  }
  // 房间颜色列表
  const roomColors = ['#fe2c55', '#5ac8fa', '#34c759']
  const roomMap = {}; let ci = 0
  Object.keys(currentRooms).forEach(rid => { roomMap[rid] = ci++ % 3 })

  let html = ''
  const sorted = filtered.sort((a, b) => mysteries[b].time - mysteries[a].time)
  sorted.forEach((secUid, idx) => {
    const m = mysteries[secUid]
    const isRegular = m.is_regular || false
    const uniqueId = m.unique_id || m.extra?.unique_id || m.sec_uid?.slice(0,12) || '?'
    const followerText = m.extra ? `粉丝${m.extra.follower_count} 作品${m.extra.aweme_count}` : ''
    const ipText = m.extra?.ip_location ? `🌍 ${m.extra.ip_location}` : ''
    const totalActions = m.chats.length + m.gifts.length
    const colorIdx = roomMap[m.room_id] !== undefined ? roomMap[m.room_id] : 0
    const roomColor = roomColors[colorIdx]

    html += `<div class="event ${isRegular ? 'regular' : 'mystery'}${m.expanded?' exp':''}" data-su="${secUid}">`
    // 房间标签 + 展开按钮
    html += `<div style="display:flex;justify-content:space-between;align-items:start">`
    html += `<div style="display:flex;align-items:center;gap:4px;flex-wrap:wrap;min-width:0;flex:1">`
    html += `<span style="font-size:10px;color:${roomColor};font-weight:600">${escapeHtml(m.room_nickname || '?')}</span>`
    if (isRegular) {
      html += ` <span class="tag reg" style="font-size:9px">普通</span>`
    } else {
      if (m.badge_level) html += ` <span class="tag lv" style="font-size:9px">🏅${m.badge_level}</span>`
      if (m.consume_level) html += ` <span class="tag dia" style="font-size:9px">💎${m.consume_level}</span>`
    }
    html += `</div>`
    html += `<span style="color:#666;font-size:11px;cursor:pointer;flex-shrink:0;user-select:none" class="toggle-btn" data-collapsed="▼ ${totalActions}条互动" onclick="toggleExpand('${secUid}')">${m.expanded ? '▲ 收起' : `▼ ${totalActions}条互动`}</span>`
    html += `</div>`
    // 名字（可点击展开）
    html += `<div class="name-box"><span class="name-text ${isRegular?'rn':'mn'}" onclick="toggleName('${secUid}')">${escapeHtml(m.real_name)}`
    if (m.display && m.display !== m.real_name) {
      let aliasHtml = escapeHtml(m.display)
      if (m.aliases && m.aliases.length > 0) {
        aliasHtml += ' <span style="color:#888;font-size:10px">/ ' + m.aliases.map(function(a){return escapeHtml(a)}).join(' / ') + '</span>'
      }
      html += `<span class="dp">${aliasHtml}</span>`
    }
    html += `</span></div>`
    html += `<div style="font-size:10px;color:#888;margin:1px 0">🆔 ${escapeHtml(uniqueId)}</div>`
    if (followerText && !isRegular) html += `<div style="font-size:10px;color:#888">📊 ${followerText}</div>`
    if (ipText) html += `<div style="font-size:10px;color:#888">${ipText}</div>`
    if (m.extra?.signature && !isRegular) html += `<div style="font-size:10px;color:#777;margin-top:1px">📝 ${escapeHtml(m.extra.signature)}</div>`
    // 统计
    html += `<div style="font-size:10px;color:#777;margin:1px 0">`
    if (m.enter_count) html += `🚪${m.enter_count}次 `
    if (m.chats.length) html += `💬${m.chats.length}条 `
    if (m.gifts.length) html += `🎁${m.gifts.length}个`
    html += `</div>`
    const secUidRaw = m.sec_uid ? m.sec_uid : ""
    if (secUidRaw) html += `<div style="font-size:10px;color:#555;margin-top:1px"><a href="https://www.douyin.com/user/${encodeURIComponent(secUidRaw)}" target="_blank" style="color:#5ac8fa;text-decoration:none">🔗 主页</a></div>`

    if (totalActions > 0) {
      html += `<div id="actions-${secUid}" style="display:${m.expanded?'block':'none'};margin-top:6px;border-top:1px solid #222;padding-top:4px">`
      m.chats.forEach(c => {
        html += `<div style="font-size:11px;color:#ccc;padding:2px 0">💬 ${escapeHtml(c.content)}</div>`
        })
        m.gifts.forEach(g => {
          html += `<div style="font-size:11px;color:#ff9500;padding:2px 0">🎁 ${escapeHtml(g.name)} x${g.count}</div>`
      })
      html += `</div>`
      html += `<div style="font-size:11px;color:#666;margin-top:2px;cursor:pointer" onclick="toggleExpand('${secUid}')">`
      html += m.expanded ? '▲ 收起' : `▼ ${totalActions}条互动`
      html += `</div>`
    }
    html += `</div>`
  })
  container.innerHTML = html
}

// 单张卡片增量更新（SSE 事件用，避免全量重绘+动画抖动）
function renderSingleCard(key) {
  const m = mysteries[key]
  if (!m || currentView === 'all') return

  const container = document.getElementById('events')
  // 移除空状态
  const empty = container.querySelector('.empty')
  if (empty) container.innerHTML = ''

  const roomColors = ['#fe2c55', '#5ac8fa', '#34c759']
  const roomMap = {}; let ci = 0
  Object.keys(currentRooms).forEach(rid => { roomMap[rid] = ci++ % 3 })

  // 生成单张卡片 HTML（复用 renderMysteries 里的卡片逻辑）
  const isRegular = m.is_regular || false
  const uniqueId = m.unique_id || m.extra?.unique_id || m.sec_uid?.slice(0,12) || '?'
  const followerText = m.extra ? `粉丝${m.extra.follower_count} 作品${m.extra.aweme_count}` : ''
  const ipText = m.extra?.ip_location ? `🌍 ${m.extra.ip_location}` : ''
  const totalActions = m.chats.length + m.gifts.length
  const colorIdx = roomMap[m.room_id] !== undefined ? roomMap[m.room_id] : 0
  const roomColor = roomColors[colorIdx]

  let cardHtml = `<div class="event ${isRegular ? 'regular' : 'mystery'}${m.expanded?' exp':''}" data-su="${key}">`
  cardHtml += `<div style="display:flex;justify-content:space-between;align-items:start">`
  cardHtml += `<div style="display:flex;align-items:center;gap:4px;flex-wrap:wrap;min-width:0;flex:1">`
  cardHtml += `<span style="font-size:10px;color:${roomColor};font-weight:600">${escapeHtml(m.room_nickname || '?')}</span>`
  if (isRegular) {
    cardHtml += ` <span class="tag reg" style="font-size:9px">普通</span>`
  } else {
    if (m.badge_level) cardHtml += ` <span class="tag lv" style="font-size:9px">🏅${m.badge_level}</span>`
    if (m.consume_level) cardHtml += ` <span class="tag dia" style="font-size:9px">💎${m.consume_level}</span>`
  }
  cardHtml += `</div>`
  cardHtml += `<span style="color:#666;font-size:11px;cursor:pointer;flex-shrink:0;user-select:none" class="toggle-btn" data-collapsed="▼ ${totalActions}条互动" onclick="toggleExpand('${key}')">${m.expanded ? '▲ 收起' : `▼ ${totalActions}条互动`}</span>`
  cardHtml += `</div>`
  cardHtml += `<div class="name-box"><span class="name-text ${isRegular?'rn':'mn'}" onclick="toggleName('${key}')">${escapeHtml(m.real_name)}`
  if (m.display && m.display !== m.real_name) {
    let aliasHtml = escapeHtml(m.display)
    if (m.aliases && m.aliases.length > 0) {
      aliasHtml += ' <span style="color:#888;font-size:10px">/ ' + m.aliases.map(function(a){return escapeHtml(a)}).join(' / ') + '</span>'
    }
    cardHtml += `<span class="dp">${aliasHtml}</span>`
  }
  cardHtml += `</span></div>`
  cardHtml += `<div style="font-size:10px;color:#888;margin:1px 0">🆔 ${escapeHtml(uniqueId)}</div>`
  if (followerText && !isRegular) cardHtml += `<div style="font-size:10px;color:#888">📊 ${followerText}</div>`
  if (ipText) cardHtml += `<div style="font-size:10px;color:#888">${ipText}</div>`
  if (m.extra?.signature && !isRegular) cardHtml += `<div style="font-size:10px;color:#777;margin-top:1px">📝 ${escapeHtml(m.extra.signature)}</div>`
  cardHtml += `<div style="font-size:10px;color:#777;margin:1px 0">`
  if (m.enter_count) cardHtml += `🚪${m.enter_count}次 `
  if (m.chats.length) cardHtml += `💬${m.chats.length}条 `
  if (m.gifts.length) cardHtml += `🎁${m.gifts.length}个`
  cardHtml += `</div>`
  const cardSecUid = m.sec_uid ? m.sec_uid : ""
  if (cardSecUid) cardHtml += `<div style="font-size:10px;color:#555;margin-top:1px"><a href="https://www.douyin.com/user/${encodeURIComponent(cardSecUid)}" target="_blank" style="color:#5ac8fa;text-decoration:none">🔗 主页</a></div>`
  if (totalActions > 0) {
    cardHtml += `<div id="actions-${key}" style="display:${m.expanded?'block':'none'};margin-top:6px;border-top:1px solid #222;padding-top:4px">`
    m.chats.forEach(c => {
      cardHtml += `<div style="font-size:11px;color:#ccc;padding:2px 0">💬 ${escapeHtml(c.content)}</div>`
    })
    m.gifts.forEach(g => {
      cardHtml += `<div style="font-size:11px;color:#ff9500;padding:2px 0">🎁 ${escapeHtml(g.name)} x${g.count}</div>`
    })
    cardHtml += `</div>`
    cardHtml += `<div style="font-size:11px;color:#666;margin-top:2px;cursor:pointer" onclick="toggleExpand('${key}')">`
    cardHtml += m.expanded ? '▲ 收起' : `▼ ${totalActions}条互动`
    cardHtml += `</div>`
  }
  cardHtml += `</div>`

  const existing = container.querySelector(`[data-su="${CSS.escape(key)}"]`)
  if (existing) {
    existing.outerHTML = cardHtml
  } else {
    container.insertAdjacentHTML('beforeend', cardHtml)
  }
}

// 历史模式：选直播间后加载跨会话记录
let _historyRoomId = null  // 当前选中的历史直播间
let _historyRoomIds = []  // 合并后该房间的全部room_ids

function renderHistory() {
  const container = document.getElementById('events')
  container.innerHTML = '<div class="empty"><div class="icon">⏳</div>加载中...</div>'

  // 直接拉取所有房间的历史记录，不分房间
  fetch('/api/history_all_all')
    .then(r => r.json())
    .then(res => {
      if (!res.success || !res.records || res.records.length === 0) {
        container.innerHTML = '<div class="empty"><div class="icon">📜</div>暂无历史记录</div>'
        return
      }

      const records = res.records
      // 渲染选择栏（精简版）
      let html = ''

      records.forEach(item => {
        const extra = item.extra || {}
        const uniqueId = extra.unique_id || item.unique_id || item.sec_uid?.slice(0, 12) || '?'
        const profileUrl = item.sec_uid ? 'https://www.douyin.com/user/' + encodeURIComponent(item.sec_uid) : null
        const roomNick = item.room_nickname || extra.room_nickname || '?'

        // 所有马甲
        let displayHtml = ''
        if (item.displays && item.displays.length > 0) {
          displayHtml = item.displays.map(function(d) {
            const display = d.display || ''
            const isCurrent = d.is_current
            const isDou = display.startsWith('dou')
            if (isCurrent) {
              return '<span style="color:#fe2c55;font-size:11px">✅ ' + escapeHtml(display) + (isDou ? ' <span style="color:#ff6b35;font-size:9px">稳定</span>' : ' <span style="color:#34c759;font-size:9px">有效</span>') + '</span>'
            } else if (isDou) {
              return '<span style="color:#888;font-size:11px">⏳ ' + escapeHtml(display) + ' <span style="color:#666;font-size:9px">仅供参考</span></span>'
            } else {
              return '<span style="color:#ff6b35;font-size:11px">❌ ' + escapeHtml(display) + ' <span style="color:#666;font-size:9px">已失效</span></span>'
            }
          }).join('<br>')
        }

        const key = item.sec_uid || item.display || '?'
        html += '<div class="event mystery" data-su="' + escapeHtml(key) + '">'
        // 房间标签
        html += '<div style="font-size:10px;color:#fe2c55;font-weight:600;margin-bottom:2px">' + escapeHtml(roomNick) + '</div>'
        // 真实名字
        const realName = escapeHtml(item.real_name || item.display || '?')
        html += '<div class="name-box">'
        html += '<span class="name-text mn" onclick="toggleName(' + "'" + escapeHtml(key) + "'" + ')">' + realName + '</span>'
        html += '</div>'
        html += '<div style="font-size:10px;color:#888;margin:1px 0">🆔 ' + escapeHtml(uniqueId) + '</div>'
        if (displayHtml) html += '<div style="font-size:11px;margin:3px 0;line-height:1.6">' + displayHtml + '</div>'
        // 最后出现时间
        if (item.last_seen) {
          const d = new Date(item.last_seen * 1000)
          html += '<div style="font-size:9px;color:#555;margin-top:2px">最后出现: ' + d.toLocaleString('zh-CN') + '</div>'
        }
        if (profileUrl) {
          html += '<div style="font-size:10px;color:#555;margin-top:3px"><a href="' + profileUrl + '" target="_blank" style="color:#5ac8fa;text-decoration:none">🔗 主页</a></div>'
        }
        html += '</div>'
      })
      container.innerHTML = html
    })
    .catch(function(e) {
      container.innerHTML = '<div class="empty"><div class="icon">❌</div>加载失败: ' + escapeHtml(String(e)) + '</div>'
    })
}

function fetchHistoryForRoom(roomId) {
  const container = document.getElementById('events')
  // 保留直播间选择栏
  const tabsHtml = container.querySelector('.room-tab') ? container.querySelector('div:first-child').outerHTML : ''

  // 如果有合并的 room_ids，全部拉取
  const roomIds = (_historyRoomIds && _historyRoomIds.length > 0) ? _historyRoomIds : [roomId]

  Promise.all(roomIds.map(rid =>
    fetch('/api/history_all?room_id=' + encodeURIComponent(rid)).then(r => r.json())
  )).then(results => {
    // 合并所有记录，按 sec_uid 去重
    const merged = {}
    results.forEach(res => {
      if (!res.success || !res.records) return
      res.records.forEach(item => {
        const key = item.sec_uid || item.display
        if (!merged[key]) {
          merged[key] = item
        } else {
          // 合并 displays（去重）
          const existing = merged[key]
          const existingDisplays = (existing.displays || []).map(d => d.display)
          const newDisplays = (item.displays || []).filter(d => !existingDisplays.includes(d.display))
          existing.displays = [...(existing.displays || []), ...newDisplays]
          // 合并 counts
          existing.enter_count = (existing.enter_count || 0) + (item.enter_count || 0)
          existing.chat_count = (existing.chat_count || 0) + (item.chat_count || 0)
          existing.gift_count = (existing.gift_count || 0) + (item.gift_count || 0)
          if ((item.last_seen || 0) > (existing.last_seen || 0)) existing.last_seen = item.last_seen
        }
      })
    })

    // 合并完成后，每个用户每种 display 类型只留最新的一个
    Object.values(merged).forEach(item => {
      const displays = item.displays || []
      if (displays.length <= 1) return
      const mystery = displays.filter(d => d.display.startsWith('神秘人'))
      const dou = displays.filter(d => d.display.startsWith('dou'))
      const other = displays.filter(d => !d.display.startsWith('神秘人') && !d.display.startsWith('dou'))
      const filtered = []
      for (const group of [mystery, dou, other]) {
        if (group.length) {
          group.sort((a, b) => (a.last_seen || 0) - (b.last_seen || 0))
          filtered.push(group[group.length - 1])
        }
      }
      filtered.sort((a, b) => (a.last_seen || 0) - (b.last_seen || 0))
      item.display = filtered[filtered.length - 1].display
      item.displays = filtered
    })

    const records = Object.values(merged).sort((a, b) => (b.last_seen || 0) - (a.last_seen || 0))

    if (records.length === 0) {
      container.innerHTML = (tabsHtml || '') + '<div class="empty"><div class="icon">📜</div>该直播间暂无神秘人历史记录</div>'
      return
    }

    // 统计 - 简洁版
    let html = tabsHtml

    records.forEach(item => {
      const extra = item.extra || {}
      const uniqueId = extra.unique_id || item.sec_uid?.slice(0, 12) || '?'
      // 主页链接
      const profileUrl = item.sec_uid ? 'https://www.douyin.com/user/' + encodeURIComponent(item.sec_uid) : null

      // 所有马甲
      let displayHtml = ''
      if (item.displays && item.displays.length > 0) {
        displayHtml = item.displays.map(function(d) {
          const display = d.display || ''
          const isCurrent = d.is_current
          const isDou = display.startsWith('dou')
          if (isCurrent) {
            return '<span style="color:#fe2c55;font-size:11px">✅ ' + escapeHtml(display) + (isDou ? ' <span style="color:#ff6b35;font-size:9px">稳定</span>' : ' <span style="color:#34c759;font-size:9px">有效</span>') + '</span>'
          } else if (isDou) {
            return '<span style="color:#888;font-size:11px">⏳ ' + escapeHtml(display) + ' <span style="color:#666;font-size:9px">仅供参考</span></span>'
          } else {
            return '<span style="color:#ff6b35;font-size:11px">❌ ' + escapeHtml(display) + ' <span style="color:#666;font-size:9px">已失效</span></span>'
          }
        }).join('<br>')
      }

      const key = item.sec_uid || item.display || '?'
      html += '<div class="event mystery" data-su="' + escapeHtml(key) + '">'
      // 真实名字（点击展开全名）+ 主页链接
      const realName = escapeHtml(item.real_name || item.display || '?')
      html += '<div class="name-box">'
      html += '<span class="name-text mn" onclick="toggleName(' + "'" + escapeHtml(key) + "'" + ')">' + realName + '</span>'
      html += '</div>'
      html += '<div style="font-size:10px;color:#888;margin:1px 0">🆔 ' + escapeHtml(uniqueId) + '</div>'
      if (displayHtml) html += '<div style="font-size:11px;margin:3px 0;line-height:1.6">' + displayHtml + '</div>'
      // 最后出现时间
      if (item.last_seen) {
        const d = new Date(item.last_seen * 1000)
        html += '<div style="font-size:9px;color:#555;margin-top:2px">最后出现: ' + d.toLocaleString('zh-CN') + '</div>'
      }
      if (profileUrl) {
        html += '<div style="font-size:10px;color:#555;margin-top:3px"><a href="' + profileUrl + '" target="_blank" style="color:#5ac8fa;text-decoration:none">🔗 主页</a></div>'
      }
      html += '</div>'
    })
    container.innerHTML = html
  }).catch(function(e) {
    container.innerHTML = (tabsHtml || '') + '<div class="empty"><div class="icon">❌</div>加载失败: ' + escapeHtml(String(e)) + '</div>'
  })
}

// 全部用户模式：从 SQLite 读取（已聚合，快）
let _allUsersCache = null  // 缓存数据，展开收起时不重复请求
let _allShowAll = false    // 全部页是否显示所有历史
function renderAllRecords(skipFetch) {
  const container = document.getElementById('events')
  let roomIds = Object.keys(currentRooms)
  if (roomIds.length === 0) {
    container.innerHTML = '<div class="empty"><div class="icon">📋</div>开始监听后自动显示数据</div>'
    return
  }
  doRenderAll(roomIds, container, skipFetch)
}

function doRenderAll(roomIds, container, skipFetch) {
  const roomColors = ['#fe2c55', '#5ac8fa', '#34c759']
  const roomMap = {}; let ci = 0
  roomIds.forEach(rid => { roomMap[rid] = ci++ % 3 })

  // 有缓存且只是展开收起，直接用缓存渲染
  if (skipFetch && _allUsersCache) {
    renderAllCards(_allUsersCache, container, roomColors, roomMap)
    return
  }

  // 显示加载中
  container.innerHTML = '<div class="empty"><div class="icon">⏳</div>同步中...</div>'

  Promise.all(roomIds.map(rid =>
    fetch('/api/all_records/' + rid + (_allShowAll ? '' : '?hours=2')).then(r => r.json())
  )).then(results => {
    const users = []
    results.forEach((res, ridx) => {
      if (!res.success || !res.records) return
      res.records.forEach(r => {
        const extra = r.extra || {}
        const secUid = r.sec_uid || r.display || '?'
        const displayNames = r.displays || []
        const isPrivate = !r.sec_uid
        // 合并同一 sec_uid 的用户
        let existing = null
        for (let i = 0; i < users.length; i++) {
          if (users[i]._key === secUid || (isPrivate && users[i].display === r.display)) {
            existing = users[i]
            break
          }
        }
        if (!existing) {
          const colorIdx = roomMap[r.room_id] !== undefined ? roomMap[r.room_id] : ridx
          existing = {
            _key: secUid,
            display: r.display || '',
            real_name: r.real_name || extra.nickname || r.display || '',
            sec_uid: r.sec_uid || '',
            unique_id: extra.unique_id || r.sec_uid || '',
            badge_level: extra.badge_level || r.badge_level || 0,
            consume_level: r.consume_level || extra.consume_level || 0,
            mystery_man: r.mystery_man || (r.is_regular ? 0 : 2) || 0,
            room_id: r.room_id,
            room_nickname: currentRooms[r.room_id]?.nickname || r.room_id,
            roomColor: roomColors[colorIdx],
            enter_count: r.enter_count || 0,
            chat_count: r.chat_count || 0,
            gift_count: r.gift_count || 0,
            chats: [], gifts: [],
            time: r.last_seen || 0,
            expanded: false,
            extra: extra,
            aliasDisplays: displayNames.filter(function(d){ return d.display !== r.display }).map(function(d){ return d.display })
          }
          users.push(existing)
        } else {
          existing.enter_count += (r.enter_count || 0)
          existing.gift_count += (r.gift_count || 0)
          existing.chat_count += (r.chat_count || 0)
          if (!existing.real_name && extra.nickname) existing.real_name = extra.nickname
          if (extra.follower_count && !existing.extra?.follower_count) existing.extra = extra
          if ((r.last_seen || 0) > existing.time) existing.time = r.last_seen
          // 收集别名
          displayNames.forEach(function(d){
            if (d.display !== existing.display && existing.aliasDisplays.indexOf(d.display) === -1) {
              existing.aliasDisplays.push(d.display)
            }
          })
        }
      })
    })
    // 合并完成后，每个用户每种 display 类型只留最新的一个
    users.forEach(function(u) {
      var ads = u.aliasDisplays || []
      if (ads.length <= 1) return
      // 按类型分组
      var m = [], d = [], o = []
      ads.forEach(function(a) {
        if (a.startsWith('神秘人')) m.push(a)
        else if (a.startsWith('dou')) d.push(a)
        else o.push(a)
      })
      var filtered = []
      if (m.length) filtered.push(m[m.length - 1])
      if (d.length) filtered.push(d[d.length - 1])
      if (o.length) filtered.push(o[o.length - 1])
      u.aliasDisplays = filtered
    })
    _allUsersCache = users.sort(function(a, b){ return b.time - a.time })
    renderAllCards(_allUsersCache, container, roomColors, roomMap)
  }).catch(function(){
    container.innerHTML = '<div class="empty" style="color:#fe2c55">加载失败</div>'
  })
}

// 渲染全部用户卡片（从缓存）
function renderAllCards(users, container, roomColors, roomMap) {
  if (users.length === 0) {
    container.innerHTML = '<div class="empty"><div class="icon">📋</div>暂无记录<br><span style="font-size:11px;color:#666">点击刷新同步最新数据</span></div>'
    return
  }

  let html = ''
  users.forEach((u, idx) => {
    const totalActions = (u.chat_count || 0) + (u.gift_count || 0)
    const uid = u.sec_uid || (u.unique_id && u.unique_id !== '?' ? u.unique_id : 'u' + idx)
    const uname = escapeHtml(u.real_name || u.display || u.unique_id || '?')
    const uniqueId = escapeHtml(u.extra?.unique_id || u.unique_id || u.sec_uid?.slice(0,12) || '?')

    const isMystery = u.mystery_man >= 2
    html += `<div class="event ${isMystery?'mystery':'regular'}${u.expanded?' exp':''}" data-su="${uid}" style="height:auto;min-height:80px">`
    html += `<div style="display:flex;justify-content:space-between;align-items:start">`
    html += `<div style="display:flex;align-items:center;gap:4px;flex-wrap:wrap;min-width:0;flex:1">`
    html += `<span style="font-size:10px;color:${u.roomColor};font-weight:600">${escapeHtml(u.room_nickname || '?')}</span>`
    html += ` <span class="tag ${isMystery?'mystery':'reg'}" style="font-size:9px${isMystery ? ';color:#fe2c55':''}">${isMystery ? '神秘人' : '普通'}</span>`
    if (u.badge_level) html += ` <span class="tag lv" style="font-size:9px">🏅${u.badge_level}</span>`
    if (u.consume_level) html += ` <span class="tag dia" style="font-size:9px">💎${u.consume_level}</span>`
    html += `</div>`
    if (totalActions > 0) {
      html += `<div style="font-size:10px;color:#666;cursor:pointer;user-select:none;white-space:nowrap" onclick="loadAllActions('${uid}','${u.room_id}')">▼ ${totalActions}条</div>`
    } else {
      html += `<div></div>`
    }
    html += `</div>`
    html += '<div class="name-box"><span class="name-text ' + (isMystery?'mn':'rn') + '" onclick="toggleName(' + "'" + uid + "'" + ')">' + escapeHtml(u.real_name || u.display || '?') + (u.display && u.display !== (u.real_name||u.display) ? '<span class="dp">' + escapeHtml(u.display) + '</span>' : '') + '</span></div>'
    // 显示别名
    if (u.aliasDisplays && u.aliasDisplays.length > 0) {
      html += '<div style="font-size:10px;color:#888;margin:1px 0">' + u.aliasDisplays.map(function(a){ return '<span style="color:#666">⏳ ' + escapeHtml(a) + '</span>' }).join(' ') + '</div>'
    }
    html += `<div style="font-size:10px;color:#888;margin:1px 0">🆔 ${uniqueId}</div>`
    // 私密直播间：有真实数据则显示粉丝数/IP/签名/主页
    if (u.extra && u.extra.nickname) {
      const ft = `粉丝${u.extra.follower_count} 作品${u.extra.aweme_count}`
      if (ft) html += `<div style="font-size:10px;color:#888">📊 ${ft}</div>`
      if (u.extra.ip_location) html += `<div style="font-size:10px;color:#888">🌍 ${escapeHtml(u.extra.ip_location)}</div>`
      if (u.extra.signature) html += `<div style="font-size:10px;color:#777;margin-top:1px">📝 ${escapeHtml(u.extra.signature)}</div>`
      if (u.sec_uid) html += `<div style="font-size:10px;color:#555;margin-top:1px"><a href="https://www.douyin.com/user/${encodeURIComponent(u.sec_uid)}" target="_blank" style="color:#5ac8fa;text-decoration:none">🔗 主页</a></div>`
    }
    html += `<div style="font-size:10px;color:#777;margin:1px 0">`
    if (u.enter_count) html += `🚪${u.enter_count}次 `
    if (u.chat_count) html += `💬${u.chat_count}条 `
    if (u.gift_count) html += `🎁${u.gift_count}个`
    html += `</div>`
    // 互动展开内容容器
    html += `<div id="acts-${uid}" style="display:none;margin-top:4px;border-top:1px solid #222;padding-top:4px"></div>`
    html += `</div>`
  })
  container.innerHTML = html + '<div style="text-align:center;margin-top:10px"><span style="font-size:12px;color:#5ac8fa;cursor:pointer;padding:6px 14px;border:1px solid #333;border-radius:8px;display:inline-block" onclick="toggleAllHistory()">' + (_allShowAll ? '📋 只看最近2小时' : '📋 查看全部历史数据') + '</span></div>'
}

// 全部用户卡片展开/收起
function toggleAllExpand(key, idx) {
  const users = _allUsersCache
  if (users && users[idx]) {
    users[idx].expanded = !users[idx].expanded
    const card = document.querySelector(`[data-su="${CSS.escape(key)}"]`)
    if (card) card.classList.toggle('exp')
    const actions = document.getElementById(`all-actions-${key}`)
    if (actions) actions.style.display = users[idx].expanded ? 'block' : 'none'
    card?.querySelectorAll('.toggle-btn').forEach(btn => {
      btn.textContent = users[idx].expanded ? '▲ 收起' : btn.dataset.collapsed
    })
  }
}

// 全部页切换：最近2小时 / 全部历史
function toggleAllHistory() {
  _allShowAll = !_allShowAll
  _allUsersCache = null  // 清缓存重新加载
  renderAllRecords()
}

// 全部页：加载并展开某用户的互动详情
function loadAllActions(uid, roomId) {
  const actDiv = document.getElementById('acts-' + uid)
  if (!actDiv) return
  if (actDiv.style.display === 'block') {
    actDiv.style.display = 'none'
    return
  }
  // 已加载过内容就直接展开
  if (actDiv.dataset.loaded) {
    actDiv.style.display = 'block'
    return
  }
  actDiv.innerHTML = '<div style="color:#666;font-size:11px">加载中...</div>'
  actDiv.style.display = 'block'
  fetch('/api/interactions/' + roomId + '/' + encodeURIComponent(uid))
    .then(r => r.json())
    .then(data => {
      if (!data.success || !data.interactions || data.interactions.length === 0) {
        actDiv.innerHTML = '<div style="color:#555;font-size:11px">暂无详细记录</div>'
        return
      }
      let html = ''
      data.interactions.slice(0, 50).forEach(function(item) {
        if (item.type === 'chat') {
          html += '<div style="font-size:11px;color:#ccc;padding:2px 0">💬 ' + escapeHtml(item.content) + '</div>'
        } else if (item.type === 'gift') {
          html += '<div style="font-size:11px;color:#ff9500;padding:2px 0">🎁 ' + escapeHtml(item.content) + ' x' + item.gift_count + '</div>'
        }
      })
      if (data.interactions.length > 50) {
        html += '<div style="font-size:10px;color:#555;margin-top:2px">仅显示最近50条</div>'
      }
      actDiv.innerHTML = html
      actDiv.dataset.loaded = '1'
    })
    .catch(function() {
      actDiv.innerHTML = '<div style="color:#fe2c55;font-size:11px">加载失败</div>'
    })
}

// ========== 公屏模式 ==========

function loadFeed() {
  const container = document.getElementById('feedContainer')
  const roomIds = Object.keys(currentRooms)
  if (roomIds.length === 0) {
    container.innerHTML = '<div class="feed-empty"><div class="icon">🖥</div>开始监听后自动显示<br><span style="font-size:11px;color:#666">公屏时间线</span></div>'
    return
  }
  container.innerHTML = '<div class="feed-empty"><div class="icon">⏳</div>加载中...</div>'

  Promise.all(roomIds.map(rid =>
    fetch('/api/feed/' + encodeURIComponent(rid) + '?limit=200').then(r => r.json())
  )).then(results => {
    const allEvents = []
    results.forEach(res => {
      if (res.success && res.events) {
        res.events.forEach(ev => allEvents.push(ev))
      }
    })
    allEvents.sort((a, b) => a.timestamp - b.timestamp)
    const merged = allEvents.slice(0, 200)
    renderFeed(merged)
  }).catch(() => {
    container.innerHTML = '<div class="feed-empty" style="color:#fe2c55">加载失败</div>'
  })
}

function renderFeed(events) {
  const container = document.getElementById('feedContainer')
  if (!events || events.length === 0) {
    container.innerHTML = '<div class="feed-empty"><div class="icon">🖥</div>暂无互动记录</div>'
    return
  }
  let html = ''
  events.forEach(ev => {
    const timeStr = formatTime(ev.timestamp)
    const name = escapeHtml(ev.real_name || ev.display || '?')
    const typeClass = ev.type === 'enter' ? 'feed-enter' : ev.type === 'chat' ? 'feed-chat' : 'feed-gift'
    let icon, bodyHtml
    if (ev.type === 'enter') {
      icon = '🚪'
      bodyHtml = `<span class="feed-name">${name}</span> 进入了直播间`
    } else if (ev.type === 'chat') {
      const content = escapeHtml(ev.content || '')
      icon = '💬'
      bodyHtml = `<span class="feed-name">${name}</span><span class="feed-content">: ${content}</span>`
    } else {
      const giftName = escapeHtml(ev.content || '?')
      const cnt = ev.count || 1
      icon = '🎁'
      bodyHtml = `<span class="feed-name">${name}</span> 送了 <span class="feed-count">${cnt}个${giftName}</span>`
    }
    html += `<div class="feed-item ${typeClass}">`
    html += `<span class="feed-icon">${icon}</span>`
    html += `<div class="feed-body">${bodyHtml}</div>`
    html += `<span class="feed-time">${timeStr}</span>`
    html += `</div>`
  })
  container.innerHTML = html
  // 自动滚动到底部
  container.scrollTop = container.scrollHeight
}

function appendFeedItem(event) {
  try {
  const container = document.getElementById('feedContainer')
  if (!container) return

  const d = event.data || event
  const timeStr = formatTime(d.timestamp || Math.floor(Date.now() / 1000))
  const name = escapeHtml(d.real_name || d.display || '?')

  let icon, bodyHtml, typeClass
  if (event.type === 'mystery_enter') {
    typeClass = 'feed-enter'; icon = '🚪'
    bodyHtml = `<span class="feed-name">${name}</span> 进入了直播间`
  } else if (event.type === 'mystery_chat') {
    typeClass = 'feed-chat'; icon = '💬'
    bodyHtml = `<span class="feed-name">${name}</span><span class="feed-content">: ${escapeHtml(d.content || '')}</span>`
  } else if (event.type === 'mystery_gift') {
    typeClass = 'feed-gift'; icon = '🎁'
    const giftName = escapeHtml(d.gift_name || d.content || '?')
    bodyHtml = `<span class="feed-name">${name}</span> 送了 <span class="feed-count">${d.count || 1}个${giftName}</span>`
  } else {
    return
  }

  // 移除空状态占位
  if (container.querySelector('.feed-empty')) {
    container.innerHTML = ''
  }

  // 直接 insertAdjacentHTML，不做 DOM 创建
  container.insertAdjacentHTML('beforeend',
    `<div class="feed-item ${typeClass}">` +
    `<span class="feed-icon">${icon}</span>` +
    `<div class="feed-body">${bodyHtml}</div>` +
    `<span class="feed-time">${timeStr}</span></div>`
  )

  // 超过 500 条时丢弃最早的
  while (container.children.length > 500) {
    container.removeChild(container.firstChild)
  }

  // 自动滚动到底部
  const isScrolledUp = container.scrollTop + container.clientHeight < container.scrollHeight - 60
  if (!isScrolledUp) {
    container.scrollTop = container.scrollHeight
  }
  } catch(e) { console.warn('[FEED] appendFeedItem error:', e) }
}

function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function toggleExpand(secUid) {
  if (mysteries[secUid]) {
    mysteries[secUid].expanded = !mysteries[secUid].expanded
    const card = document.querySelector(`[data-su="${CSS.escape(secUid)}"]`)
    if (card) card.classList.toggle('exp')
    const actions = document.getElementById(`actions-${secUid}`)
    if (actions) actions.style.display = mysteries[secUid].expanded ? 'block' : 'none'
    card?.querySelectorAll('.toggle-btn').forEach(btn => {
      btn.textContent = mysteries[secUid].expanded ? '▲ 收起' : btn.dataset.collapsed
    })
  }
}

// 点击名字展开/收起截断
function toggleName(secUid) {
  const card = document.querySelector(`[data-su="${secUid}"]`)
  if (card) {
    const nameEl = card.querySelector('.name-text')
    if (nameEl) nameEl.classList.toggle('exp')
  }
}

// 回车提交
document.getElementById('input').addEventListener('keydown', function(e) {
  if (e.key === 'Enter') connect()
});
// 输入时动态切换按钮文字
document.getElementById('input').addEventListener('keyup', resetBtnText)
document.getElementById('input').addEventListener('blur', resetBtnText)

// ========== 搜索历史下拉 ==========
document.getElementById('input').addEventListener('focus', function() {
  loadRoomHistory()
})
document.getElementById('input').addEventListener('blur', function() {
  // 延迟隐藏，给点击 dropdown 留时间
  setTimeout(() => {
    document.getElementById('historyDropdown').style.display = 'none'
  }, 200)
})

// 定时刷新活跃房间列表
setInterval(refreshRooms, 5000)

function refreshRooms() {
  fetch('/api/status')
    .then(r => r.json())
    .then(data => {
      if (data.count > 0) {
        document.getElementById('statsText').textContent = `${data.count}/${data.max}房`
      } else {
        document.getElementById('statsText').textContent = '0房'
      }
    })
}

function stopRoom(roomId) {
  // 关闭SSE
  if (eventSources[roomId]) {
    eventSources[roomId].close()
    delete eventSources[roomId]
  }
  if (disconnectTimers[roomId]) {
    clearTimeout(disconnectTimers[roomId])
    delete disconnectTimers[roomId]
  }
  // 移除该房间的神秘人
  Object.keys(mysteries).forEach(secUid => {
    if (mysteries[secUid].room_id === roomId) {
      delete mysteries[secUid]
    }
  })
  delete currentRooms[roomId]
  renderMysteries()
  fetch('/api/stop', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({room_id: roomId})
  }).then(() => {
    if (Object.keys(currentRooms).length === 0) {
      document.getElementById('btn').textContent = '🔍 监听'
      document.getElementById('btn').className = ''
      lastRoomId = null
      setStatus('未连接', 'gray')
      document.getElementById('anonymousBanner').classList.remove('show')
    }
    refreshRooms()
  })
}

function stopAll() {
  // 关闭所有SSE
  Object.keys(eventSources).forEach(rid => {
    eventSources[rid].close()
  })
  eventSources = {}
  disconnectTimers = {}
  Object.keys(mysteries).forEach(k => delete mysteries[k])
  Object.keys(currentRooms).forEach(k => delete currentRooms[k])
  document.getElementById('btn').textContent = '🔍 监听'
  document.getElementById('btn').className = ''
  lastRoomId = null
  setStatus('未连接', 'gray')
  document.getElementById('anonymousBanner').classList.remove('show')
  document.getElementById('events').innerHTML = '<div class="empty"><div class="icon">🎯</div>已停止</div>'
  fetch('/api/stop_all', {method: 'POST'}).then(() => refreshRooms())
}

// 页面加载时：检测服务端是否已有监听中的房间，自动重连
;(function autoReconnectOnLoad() {
  fetch('/api/status')
    .then(r => r.json())
    .then(data => {
      if (data.count > 0) {
        data.active.forEach(r => {
          currentRooms[r.room_id] = {nickname: r.nickname || r.room_id}
          connectSSE(r.room_id)
        })
        lastRoomId = data.active[0].room_id
        document.getElementById('btn').textContent = '停止'
        document.getElementById('btn').className = 'stop-btn'
        setStatus('监听中', 'green')
        document.getElementById('events').innerHTML = '<div class="empty"><div class="icon">🎯</div>等待神秘人出现...</div>'
      }
    })
    .catch(() => {})
})()

/* ═══ Anime.js 动画增强 ═══ */
const { animate, stagger, spring } = anime;

/* ---- 状态圆点呼吸 ---- */
(function dotPulse(){
  const dot = document.getElementById('dot');
  let anim = null;
  const obs = new MutationObserver(() => {
    if(anim) { anim.pause(); anim = null; }
    if(dot.classList.contains('green')){
      anim = animate(dot, {
        boxShadow: ['0 0 0 0 rgba(52,199,89,0)', '0 0 0 6px rgba(52,199,89,0.3)'],
        duration: 1500,
        loop: true,
        ease: 'inOutSine',
      });
    } else if(dot.classList.contains('red')){
      anim = animate(dot, {
        boxShadow: ['0 0 0 0 rgba(255,59,48,0)', '0 0 0 5px rgba(255,59,48,0.2)'],
        duration: 1200,
        loop: true,
        ease: 'inOutSine',
      });
    } else {
      dot.style.boxShadow = 'none';
    }
  });
  obs.observe(dot, { attributes: true, attributeFilter: ['class'] });
})();

/* ---- 按钮监听光晕 ---- */
(function btnGlow(){
  const btn = document.getElementById('btn');
  let glow = null;
  const obs = new MutationObserver(() => {
    if(glow) { glow.pause(); glow = null; }
    if(btn.classList.contains('stop-btn')){
      btn.style.transition = 'box-shadow .3s';
      glow = animate(btn, {
        boxShadow: ['0 0 0 0 rgba(255,107,53,0)', '0 0 12px 3px rgba(255,107,53,0.25)'],
        duration: 2000,
        loop: true,
        ease: 'inOutSine',
      });
    } else {
      btn.style.boxShadow = 'none';
    }
  });
  obs.observe(btn, { attributes: true, attributeFilter: ['class'] });
})();

/* ---- Hook renderMysteries 添加卡片动画 ---- */
const origRender = renderMysteries;
renderMysteries = function(){
  origRender();
  const cards = document.querySelectorAll('.events > .event');
  cards.forEach(c => { c.style.opacity = '0'; c.style.transform = 'translateY(8px)'; });
  animate(cards, {
    opacity: [0,1],
    translateY: [8,0],
    duration: 400,
    delay: stagger(60),
    ease: 'outCubic',
  });
};

/* ---- Hook renderAllCards 添加卡片动画 ---- */
const origRenderAll = renderAllCards;
renderAllCards = function(users, container, roomColors, roomMap){
  origRenderAll(users, container, roomColors, roomMap);
  const cards = document.querySelectorAll('.events > .event');
  cards.forEach(c => { c.style.opacity = '0'; c.style.transform = 'translateY(8px)'; });
  animate(cards, {
    opacity: [0,1],
    translateY: [8,0],
    duration: 400,
    delay: stagger(60),
    ease: 'outCubic',
  });
};

/* ---- 模式切换卡片动画 ---- */
const origSwitch = switchMode;
switchMode = function(mode){
  origSwitch(mode);
  // 切换后卡片已有新内容，动画在 render 函数里已触发
};

// 页面加载时预搜索历史缓存
refreshHistoryCache();

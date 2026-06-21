"""抖音表情图片抓取脚本
从 emojiall.com 抓取抖音最新表情图片，保存到 static/emoji/
并生成 emoji_map.json 映射文件
"""

import os, json, re, time, hashlib
import requests
from bs4 import BeautifulSoup

EMOJI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'emoji')
MAPPING_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'emoji_map.json')
URL = 'https://www.emojiall.com/zh-hans/platform-douyin'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
}

def ensure_dir():
    os.makedirs(EMOJI_DIR, exist_ok=True)

def fetch_page(url):
    """抓取页面 HTML"""
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text

def parse_emoji_mapping(html):
    """解析页面中的表情映射"""
    soup = BeautifulSoup(html, 'html.parser')
    mapping = {}  # 名字 -> {image_url, unicode_emoji}
    
    # 找到所有表格行
    # 页面结构：表格，每行有图片、名字、对应 Emoji
    tables = soup.find_all('table')
    
    for table in tables:
        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 2:
                continue
            
            # 第一列是图片+名字
            first_cell = cells[0]
            img_tag = first_cell.find('img')
            if not img_tag:
                continue
            
            img_url = img_tag.get('src', '') or img_tag.get('data-src', '')
            if not img_url:
                continue
            
            # 提取名字（在 img 后面的文本，或 title）
            name = ''
            # 尝试从 title 属性取
            title = img_tag.get('title', '') or img_tag.get('alt', '')
            if title:
                # title 通常是 "[爱心] ❤ 红心" 这种格式
                match = re.match(r'\[([^\]]+)\]', title)
                if match:
                    name = match.group(1)
            
            # 如果 title 没取到，从单元格文本取
            if not name:
                text = first_cell.get_text(strip=True)
                match = re.match(r'\[([^\]]+)\]', text)
                if match:
                    name = match.group(1)
            
            if not name:
                continue
            
            # 第二列（如果有）是对应的 Unicode 表情
            unicode_emoji = ''
            if len(cells) >= 3:
                third_cell = cells[2]
                emoji_match = re.match(r'([\U0001F000-\U0010FFFF\2000-\uFFFF]+)', third_cell.get_text(strip=True))
                if emoji_match:
                    unicode_emoji = emoji_match.group(1)
            
            # 处理图片 URL（去掉过期签名）
            # 原始 URL 类似：https://p3-pc-sign.douyinpic.com/obj/tos-cn-i-tsj2vxp0zn/HASH?x-expires=...&x-signature=...&from=...
            # 去掉签名参数，只留基础路径
            # 补全完整 URL
            if img_url.startswith('/'):
                full_url = 'https://www.emojiall.com' + img_url
            else:
                full_url = img_url
            full_url = re.sub(r'\?.*$', '', full_url)
            
            mapping[name] = {
                'image_url': full_url,
                'unicode_emoji': unicode_emoji,
                'name': name
            }
            print(f"  [√] {name} (Emoji: {unicode_emoji or '无'}) -> {full_url}")
    
    return mapping

def parse_logo_emoji(html):
    """解析 Logo 类表情（没有对应 Unicode 的）"""
    soup = BeautifulSoup(html, 'html.parser')
    mapping = {}
    
    # Logo 表情的表格：2 列，图片 + 名字
    tables = soup.find_all('table')
    
    for table in tables:
        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 2:
                continue
            
            # 检查是不是 Logo 表（没有第三列）
            if len(cells) >= 3:
                continue  # 跳过已有对应 Emoji 的表
            
            first_cell = cells[0]
            img_tag = first_cell.find('img')
            if not img_tag:
                continue
            
            img_url = img_tag.get('src', '') or img_tag.get('data-src', '')
            if not img_url:
                continue
            
            # 提取名字
            name = ''
            title = img_tag.get('title', '') or img_tag.get('alt', '')
            if title:
                match = re.match(r'\[([^\]]+)\]', title)
                if match:
                    name = match.group(1)
            
            if not name:
                text = first_cell.get_text(strip=True)
                match = re.match(r'\[([^\]]+)\]', text)
                if match:
                    name = match.group(1)
            
            if not name:
                continue
            
            # 已经存在于前面的映射中则跳过
            if name in mapping:
                continue
            
            # 补全完整 URL
            if img_url.startswith('/'):
                full_url = 'https://www.emojiall.com' + img_url
            else:
                full_url = img_url
            full_url = re.sub(r'\?.*$', '', full_url)
            mapping[name] = {
                'image_url': full_url,
                'unicode_emoji': '',
                'name': name
            }
            print(f"  [√] {name} (Logo) -> {full_url}")
    
    return mapping

def download_image(url, save_path):
    """下载图片到本地"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        with open(save_path, 'wb') as f:
            f.write(resp.content)
        return True
    except Exception as e:
        print(f"  [×] 下载失败 {url}: {e}")
        return False

def main():
    ensure_dir()
    print("=" * 50)
    print("📥 抓取抖音表情列表...")
    print("=" * 50)
    
    html = fetch_page(URL)
    
    print("\n--- 有对应 Unicode 的表情（主表） ---")
    mapping = parse_emoji_mapping(html)
    
    print(f"\n共解析 {len(mapping)} 个表情映射")
    print("\n" + "=" * 50)
    print(f"📦 开始下载 {len(mapping)} 个表情图片...")
    print("=" * 50)
    
    download_count = 0
    failed = []
    
    for name, info in mapping.items():
        # 文件名用名字的 MD5 前8位，避免特殊字符
        file_hash = hashlib.md5(name.encode('utf-8')).hexdigest()[:8]
        # 也保存名字映射，方便定位
        save_name = f"{file_hash}.png"
        save_path = os.path.join(EMOJI_DIR, save_name)
        
        # 如果文件已存在，跳过
        if os.path.exists(save_path):
            print(f"  [-] {name} 已存在")
            info['local_file'] = save_name
            download_count += 1
            continue
        
        # 用原始 URL 下载（去掉过期签名）
        url = info['image_url']
        if download_image(url, save_path):
            info['local_file'] = save_name
            download_count += 1
            print(f"  [√] {name} -> {save_name}")
        else:
            # fallback: 尝试使用带签名的原始 URL
            # 从页面重新获取完整 URL
            print(f"  [?] {name} 尝试备用方式...")
            failed.append(name)
        
        time.sleep(0.2)  # 礼貌性延迟
    
    # 保存映射文件
    mapping_output = {}
    for name, info in mapping.items():
        if info.get('local_file'):
            mapping_output[name] = {
                'file': info['local_file'],
                'emoji': info.get('unicode_emoji', ''),
                'name': name
            }
    
    with open(MAPPING_FILE, 'w', encoding='utf-8') as f:
        json.dump(mapping_output, f, ensure_ascii=False, indent=2)
    
    print("\n" + "=" * 50)
    print(f"✅ 完成！")
    print(f"   下载成功: {len(mapping_output)}/{len(mapping)}")
    print(f"   下载失败: {len(failed)}")
    print(f"   图片目录: {EMOJI_DIR}")
    print(f"   映射文件: {MAPPING_FILE}")
    print("=" * 50)
    
    if failed:
        print(f"\n⚠️ 以下表情下载失败: {', '.join(failed)}")

if __name__ == '__main__':
    main()

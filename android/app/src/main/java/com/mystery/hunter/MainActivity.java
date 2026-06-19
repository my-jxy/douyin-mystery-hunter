package com.mystery.hunter;

import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.view.MenuItem;
import android.widget.CompoundButton;
import android.widget.Toast;
import androidx.annotation.NonNull;
import androidx.appcompat.app.AlertDialog;
import androidx.appcompat.app.AppCompatActivity;
import androidx.appcompat.widget.SwitchCompat;
import androidx.fragment.app.Fragment;
import androidx.viewpager2.adapter.FragmentStateAdapter;
import androidx.viewpager2.widget.ViewPager2;
import com.google.android.material.bottomnavigation.BottomNavigationView;
import com.mystery.hunter.ui.AllRecordsFragment;
import com.mystery.hunter.ui.MonitoringFragment;
import com.mystery.hunter.ui.MysteryFragment;
import com.mystery.hunter.ui.SearchFragment;

public class MainActivity extends AppCompatActivity {

    private static final int REQUEST_OVERLAY = 1001;
    private BottomNavigationView bottomNav;
    private ViewPager2 viewPager;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        bottomNav = findViewById(R.id.bottom_nav);
        viewPager = findViewById(R.id.view_pager);

        viewPager.setAdapter(new MainPagerAdapter(this));
        viewPager.setOffscreenPageLimit(3);
        viewPager.registerOnPageChangeCallback(new ViewPager2.OnPageChangeCallback() {
            @Override
            public void onPageSelected(int position) {
                bottomNav.getMenu().getItem(position).setChecked(true);
            }
        });

        bottomNav.setOnItemSelectedListener(item -> {
            int id = item.getItemId();
            if (id == R.id.nav_monitoring) viewPager.setCurrentItem(0, true);
            else if (id == R.id.nav_mystery) viewPager.setCurrentItem(1, true);
            else if (id == R.id.nav_all_records) viewPager.setCurrentItem(2, true);
            else if (id == R.id.nav_search) viewPager.setCurrentItem(3, true);
            return true;
        });

        // 检查悬浮窗权限
        checkOverlayPermission();
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        // 从悬浮窗点击进入时，bring to front 已由 FLAG_ACTIVITY_REORDER_TO_FRONT 处理
    }

    private void checkOverlayPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            if (!Settings.canDrawOverlays(this)) {
                new AlertDialog.Builder(this)
                        .setTitle("需要悬浮窗权限")
                        .setMessage(R.string.permission_overlay_required)
                        .setPositiveButton(R.string.go_to_settings, (d, w) -> {
                            Intent intent = new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                                    Uri.parse("package:" + getPackageName()));
                            startActivityForResult(intent, REQUEST_OVERLAY);
                        })
                        .setNegativeButton(R.string.cancel, (d, w) -> d.dismiss())
                        .show();
            } else {
                // 权限已开启，可以自动启动悬浮窗
                maybeStartFloatingService();
            }
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQUEST_OVERLAY) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                if (Settings.canDrawOverlays(this)) {
                    Toast.makeText(this, "悬浮窗权限已开启", Toast.LENGTH_SHORT).show();
                    maybeStartFloatingService();
                } else {
                    Toast.makeText(this, "悬浮窗权限被拒绝", Toast.LENGTH_SHORT).show();
                }
            }
        }
    }

    private void maybeStartFloatingService() {
        if (!FloatingWindowService.isRunning(this)) {
            MysteryHunterApp.getInstance().startFloatingService();
        }
    }

    @Override
    public boolean onCreateOptionsMenu(android.view.Menu menu) {
        getMenuInflater().inflate(R.menu.main_menu, menu);
        // 悬浮窗开关
        MenuItem toggleItem = menu.findItem(R.id.action_floating_toggle);
        if (toggleItem != null && toggleItem.getActionView() != null) {
            SwitchCompat sw = toggleItem.getActionView().findViewById(R.id.sw_floating);
            if (sw != null) {
                sw.setChecked(FloatingWindowService.isRunning(this));
                sw.setOnCheckedChangeListener((buttonView, isChecked) -> {
                    if (isChecked) {
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M
                                && !Settings.canDrawOverlays(MainActivity.this)) {
                            buttonView.setChecked(false);
                            checkOverlayPermission();
                            return;
                        }
                        MysteryHunterApp.getInstance().startFloatingService();
                        Toast.makeText(MainActivity.this, "悬浮窗已开启", Toast.LENGTH_SHORT).show();
                    } else {
                        MysteryHunterApp.getInstance().stopFloatingService();
                        Toast.makeText(MainActivity.this, "悬浮窗已关闭", Toast.LENGTH_SHORT).show();
                    }
                });
            }
        }
        return true;
    }

    // -- ViewPager2 Adapter --
    private static class MainPagerAdapter extends FragmentStateAdapter {

        MainPagerAdapter(@NonNull AppCompatActivity activity) {
            super(activity);
        }

        @NonNull
        @Override
        public Fragment createFragment(int position) {
            switch (position) {
                case 0: return new MonitoringFragment();
                case 1: return new MysteryFragment();
                case 2: return new AllRecordsFragment();
                case 3: return new SearchFragment();
                default: return new MonitoringFragment();
            }
        }

        @Override
        public int getItemCount() { return 4; }
    }
}

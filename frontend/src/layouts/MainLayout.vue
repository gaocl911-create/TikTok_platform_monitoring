<script setup lang="ts">
import { DataAnalysis, Monitor, Setting } from '@element-plus/icons-vue'
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const title = computed(() => route.meta.title || '创作者监测')
</script>

<template>
  <div class="shell">
    <aside class="sidebar">
      <RouterLink class="brand" to="/" aria-label="返回监测总览">
        <span class="brand-mark">CM</span>
        <span>
          <strong>创作者监测</strong>
          <small>Creator Monitor</small>
        </span>
      </RouterLink>

      <nav aria-label="主导航">
        <RouterLink to="/" exact-active-class="active">
          <el-icon><DataAnalysis /></el-icon>
          <span>监测总览</span>
        </RouterLink>
        <RouterLink to="/creators" active-class="active">
          <el-icon><Monitor /></el-icon>
          <span>监控账号</span>
        </RouterLink>
      </nav>

      <div class="sidebar-footer">
        <el-icon><Setting /></el-icon>
        <span>Mock 数据模式</span>
      </div>
    </aside>

    <section class="page-shell">
      <header class="topbar">
        <div>
          <p>抖音 / 小红书公开数据</p>
          <h1>{{ title }}</h1>
        </div>
        <div class="topbar-status">
          <span></span>
          监控服务运行中
        </div>
      </header>
      <main>
        <RouterView />
      </main>
    </section>
  </div>
</template>

<style scoped>
.shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 224px minmax(0, 1fr);
}

.sidebar {
  position: sticky;
  top: 0;
  height: 100vh;
  display: flex;
  flex-direction: column;
  padding: 20px 14px;
  color: var(--sidebar-text);
  background: var(--sidebar);
}

.brand {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 4px 8px 24px;
  color: #ffffff;
  text-decoration: none;
}

.brand-mark {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border-radius: 7px;
  color: #062b27;
  background: var(--primary-soft);
  font-size: 12px;
  font-weight: 800;
}

.brand strong,
.brand small {
  display: block;
}

.brand strong {
  font-size: 14px;
}

.brand small {
  margin-top: 2px;
  color: #83909f;
  font-size: 10px;
}

nav {
  display: grid;
  gap: 4px;
}

nav a {
  min-height: 44px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 12px;
  border-radius: 6px;
  color: #9aa6b4;
  text-decoration: none;
  font-size: 13px;
  transition:
    color 160ms ease,
    background-color 160ms ease;
}

nav a:hover,
nav a.active {
  color: #ffffff;
  background: #263444;
}

.sidebar-footer {
  min-height: 44px;
  display: flex;
  align-items: center;
  gap: 9px;
  margin-top: auto;
  padding: 0 10px;
  border-top: 1px solid #293644;
  color: #83909f;
  font-size: 12px;
}

.page-shell {
  min-width: 0;
}

.topbar {
  height: 82px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 28px;
  border-bottom: 1px solid var(--border);
  background: var(--surface);
}

.topbar p,
.topbar h1 {
  margin: 0;
}

.topbar p {
  color: var(--text-muted);
  font-size: 11px;
}

.topbar h1 {
  margin-top: 3px;
  color: var(--text-strong);
  font-size: 21px;
}

.topbar-status {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--text-muted);
  font-size: 12px;
}

.topbar-status span {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--success);
}

main {
  padding: 24px 28px 36px;
}

@media (max-width: 760px) {
  .shell {
    width: 100%;
    max-width: 100vw;
    grid-template-columns: 1fr;
    overflow-x: hidden;
  }

  .sidebar {
    position: static;
    width: 100%;
    height: auto;
    display: block;
    padding: 10px 14px;
  }

  .brand,
  .sidebar-footer {
    display: none;
  }

  nav {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  nav a {
    justify-content: center;
  }

  .topbar {
    height: 72px;
    padding: 0 16px;
  }

  .topbar-status {
    display: none;
  }

  main {
    width: 100%;
    min-width: 0;
    padding: 16px;
  }
}
</style>

<script setup lang="ts">
const metrics = [
  { label: '监控账号', value: '0', hint: '等待添加账号' },
  { label: '今日新动态', value: '0', hint: '暂无新内容' },
  { label: '待处理预警', value: '0', hint: '运行状态正常' },
  { label: '任务成功率', value: '--', hint: '尚未开始采集' },
]
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">CM</div>
        <div>
          <strong>创作者监测</strong>
          <span>Creator Monitor</span>
        </div>
      </div>

      <nav>
        <a class="active" href="#">总览</a>
        <a href="#">监控账号</a>
        <a href="#">内容动态</a>
        <a href="#">评论线索</a>
        <a href="#">预警中心</a>
        <a href="#">采集任务</a>
      </nav>
    </aside>

    <main>
      <header>
        <div>
          <p>2026 年 6 月 4 日</p>
          <h1>监测总览</h1>
        </div>
        <button type="button">添加监控账号</button>
      </header>

      <section class="metrics" aria-label="关键指标">
        <article v-for="metric in metrics" :key="metric.label">
          <span>{{ metric.label }}</span>
          <strong>{{ metric.value }}</strong>
          <small>{{ metric.hint }}</small>
        </article>
      </section>

      <section class="workspace">
        <div>
          <div class="section-heading">
            <h2>最新动态</h2>
            <span>跨平台内容流</span>
          </div>
          <div class="empty-state">
            <strong>还没有监控动态</strong>
            <p>添加第一个抖音或小红书账号后，新发布的公开内容会显示在这里。</p>
          </div>
        </div>

        <aside class="status-panel">
          <div class="section-heading">
            <h2>系统状态</h2>
            <span class="healthy">基础骨架已就绪</span>
          </div>
          <dl>
            <div><dt>FastAPI</dt><dd>待启动</dd></div>
            <div><dt>MySQL</dt><dd>待启动</dd></div>
            <div><dt>Redis</dt><dd>待启动</dd></div>
            <div><dt>Celery Worker</dt><dd>待启动</dd></div>
          </dl>
        </aside>
      </section>
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
}

.sidebar {
  padding: 24px 16px;
  color: #e5e7eb;
  background: #111827;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 8px 28px;
}

.brand-mark {
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border-radius: 6px;
  color: #111827;
  background: #34d399;
  font-size: 13px;
  font-weight: 800;
}

.brand strong,
.brand span {
  display: block;
}

.brand span {
  margin-top: 3px;
  color: #9ca3af;
  font-size: 11px;
}

nav {
  display: grid;
  gap: 4px;
}

nav a {
  padding: 10px 12px;
  border-radius: 6px;
  color: #9ca3af;
  text-decoration: none;
  font-size: 14px;
}

nav a:hover,
nav a.active {
  color: #ffffff;
  background: #263244;
}

main {
  min-width: 0;
  padding: 28px 32px;
}

header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 28px;
}

header p,
header h1 {
  margin: 0;
}

header p {
  color: #6b7280;
  font-size: 13px;
}

header h1 {
  margin-top: 4px;
  font-size: 26px;
}

button {
  border: 0;
  border-radius: 6px;
  padding: 10px 16px;
  color: #ffffff;
  background: #0f766e;
  cursor: pointer;
  font-weight: 600;
}

.metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  overflow: hidden;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #e5e7eb;
}

.metrics article {
  min-height: 124px;
  padding: 20px;
  background: #ffffff;
}

.metrics span,
.metrics strong,
.metrics small {
  display: block;
}

.metrics span {
  color: #6b7280;
  font-size: 13px;
}

.metrics strong {
  margin: 12px 0 8px;
  color: #111827;
  font-size: 28px;
}

.metrics small {
  color: #9ca3af;
}

.workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 28px;
  margin-top: 28px;
}

.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.section-heading h2 {
  margin: 0;
  font-size: 17px;
}

.section-heading span {
  color: #9ca3af;
  font-size: 12px;
}

.empty-state,
.status-panel {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #ffffff;
}

.empty-state {
  min-height: 300px;
  display: grid;
  align-content: center;
  justify-items: center;
  padding: 32px;
  text-align: center;
}

.empty-state p {
  max-width: 420px;
  margin: 8px 0 0;
  color: #6b7280;
  line-height: 1.7;
  font-size: 13px;
}

.status-panel {
  align-self: start;
  padding: 18px;
}

.healthy {
  color: #047857 !important;
}

dl {
  margin: 0;
}

dl div {
  display: flex;
  justify-content: space-between;
  padding: 12px 0;
  border-top: 1px solid #f0f1f3;
  font-size: 13px;
}

dt {
  color: #4b5563;
}

dd {
  margin: 0;
  color: #9ca3af;
}

@media (max-width: 960px) {
  .app-shell {
    grid-template-columns: 1fr;
  }

  .sidebar {
    display: none;
  }

  main {
    padding: 20px;
  }

  .metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .workspace {
    grid-template-columns: 1fr;
  }
}
</style>

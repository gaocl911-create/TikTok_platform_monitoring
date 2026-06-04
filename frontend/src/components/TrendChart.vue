<script setup lang="ts">
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsOption } from 'echarts'
import { computed } from 'vue'
import VChart from 'vue-echarts'

import type { CreatorSnapshot } from '../types/creator'
import { formatApiTime } from '../utils/datetime'

use([CanvasRenderer, GridComponent, LineChart, TooltipComponent])

const props = defineProps<{
  snapshots: CreatorSnapshot[]
  metric: 'follower_count' | 'total_like_count'
}>()

const option = computed<EChartsOption>(() => ({
  animationDuration: 220,
  grid: { top: 18, right: 18, bottom: 30, left: 58 },
  tooltip: {
    trigger: 'axis',
    valueFormatter: (value) => Number(value).toLocaleString('zh-CN'),
  },
  xAxis: {
    type: 'category',
    boundaryGap: false,
    data: props.snapshots.map((snapshot) => formatApiTime(snapshot.captured_at)),
    axisLine: { lineStyle: { color: '#dfe4ea' } },
    axisLabel: { color: '#77808c', fontSize: 11 },
  },
  yAxis: {
    type: 'value',
    scale: true,
    axisLabel: {
      color: '#77808c',
      fontSize: 11,
      formatter: (value: number) => value.toLocaleString('zh-CN'),
    },
    splitLine: { lineStyle: { color: '#eef1f4' } },
  },
  series: [
    {
      type: 'line',
      smooth: true,
      symbolSize: 7,
      showSymbol: props.snapshots.length < 20,
      data: props.snapshots.map((snapshot) => snapshot[props.metric]),
      lineStyle: { color: '#0f766e', width: 2 },
      itemStyle: { color: '#0f766e' },
      areaStyle: { color: 'rgba(15, 118, 110, 0.08)' },
    },
  ],
}))
</script>

<template>
  <VChart class="chart" :option="option" autoresize />
</template>

<style scoped>
.chart {
  width: 100%;
  height: 300px;
}
</style>

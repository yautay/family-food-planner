<script setup>
import { computed } from 'vue'

const props = defineProps({
  time: {
    type: String,
    default: '',
  },
  size: {
    type: Number,
    default: 20,
  },
})

function normalizeTimeValue(value) {
  if (typeof value !== 'string') {
    return null
  }

  const candidate = value.trim()
  const match = candidate.match(/^(\d{2}):(\d{2})$/)
  if (!match) {
    return null
  }

  const hours = Number(match[1])
  const minutes = Number(match[2])
  if (!Number.isInteger(hours) || !Number.isInteger(minutes)) {
    return null
  }

  if (hours < 0 || hours > 23 || minutes < 0 || minutes > 59) {
    return null
  }

  return {
    hours,
    minutes,
    text: `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`,
  }
}

const parsedTime = computed(() => normalizeTimeValue(props.time))

const handAngles = computed(() => {
  if (!parsedTime.value) {
    return {
      hour: 0,
      minute: 0,
    }
  }

  const minuteAngle = parsedTime.value.minutes * 6
  const hourAngle = ((parsedTime.value.hours % 12) + parsedTime.value.minutes / 60) * 30

  return {
    hour: hourAngle,
    minute: minuteAngle,
  }
})

const clockStyle = computed(() => {
  const pixelSize = Number.isFinite(props.size) && props.size > 0 ? props.size : 20
  return {
    '--clock-size': `${pixelSize}px`,
    '--tooltip-width': `${Math.max(pixelSize * 3.8, 86)}px`,
    '--tooltip-height': `${Math.max(pixelSize * 1.9, 38)}px`,
    '--tooltip-font-size': `${Math.max(pixelSize * 0.82, 18)}px`,
    '--hour-angle': `${handAngles.value.hour}deg`,
    '--minute-angle': `${handAngles.value.minute}deg`,
  }
})

const displayText = computed(() => parsedTime.value?.text ?? '--:--')
</script>

<template>
  <span class="slot-time-clock" :style="clockStyle" :aria-label="displayText" tabindex="0">
    <span class="clock-face analog-face" role="img" :aria-label="displayText">
      <span class="dial-ring"></span>
      <span class="dial-center"></span>
      <span class="hand hand-hour"></span>
      <span class="hand hand-minute"></span>
    </span>

    <span class="digital-tooltip" aria-hidden="true">
      <span class="digital-window">{{ displayText }}</span>
    </span>
  </span>
</template>

<style scoped>
.slot-time-clock {
  --clock-size: 20px;
  --tooltip-width: 86px;
  --tooltip-height: 38px;
  --tooltip-font-size: 18px;
  --hour-angle: 0deg;
  --minute-angle: 0deg;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  position: relative;
  width: var(--clock-size);
  height: var(--clock-size);
  vertical-align: middle;
  outline: none;
}

.slot-time-clock:focus-visible {
  box-shadow: 0 0 0 2px color-mix(in oklab, var(--app-link), #ffffff 30%);
  border-radius: 999px;
}

.clock-face {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
}

.analog-face {
  border-radius: 999px;
  background: radial-gradient(circle at 30% 30%, #ffffff 0%, #e7edf8 72%);
  box-shadow: inset 0 0 0 1px color-mix(in oklab, var(--app-border), #ffffff 25%);
}

.dial-ring {
  position: absolute;
  inset: 2px;
  border-radius: 999px;
  border: 1px solid rgba(31, 95, 212, 0.35);
}

.dial-center {
  width: 3px;
  height: 3px;
  border-radius: 999px;
  background: #1f5fd4;
  position: relative;
  z-index: 3;
}

.hand {
  position: absolute;
  left: 50%;
  top: 50%;
  transform-origin: 50% 100%;
  border-radius: 999px;
}

.hand-hour {
  width: 2px;
  height: 22%;
  margin-left: -1px;
  margin-top: -22%;
  background: #35507f;
  transform: rotate(var(--hour-angle));
}

.hand-minute {
  width: 1px;
  height: 33%;
  margin-left: -0.5px;
  margin-top: -33%;
  background: #1f5fd4;
  transform: rotate(var(--minute-angle));
}

.digital-tooltip {
  position: absolute;
  left: 50%;
  top: calc(100% + 8px);
  transform: translateX(-50%) rotateX(-78deg) scale(0.82);
  transform-origin: top center;
  border-radius: 9px;
  width: var(--tooltip-width);
  height: var(--tooltip-height);
  background: linear-gradient(180deg, #eff7ff 0%, #d8e8ff 100%);
  box-shadow:
    0 12px 24px rgba(17, 42, 84, 0.2),
    inset 0 0 0 1px rgba(31, 95, 212, 0.42);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  pointer-events: none;
  transition:
    opacity 190ms ease,
    transform 260ms ease;
  z-index: 25;
}

.digital-window {
  color: #13325f;
  font-size: var(--tooltip-font-size);
  line-height: 1;
  font-weight: 700;
  letter-spacing: 0.08em;
  font-family: 'Courier Prime', 'Courier New', monospace;
  font-variant-numeric: tabular-nums;
  text-shadow: 0 0 10px rgba(52, 112, 196, 0.45);
}

.slot-time-clock:hover .digital-tooltip,
.slot-time-clock:focus-visible .digital-tooltip {
  opacity: 1;
  transform: translateX(-50%) rotateX(0deg) scale(1);
}
</style>

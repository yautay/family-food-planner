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
    '--hour-angle': `${handAngles.value.hour}deg`,
    '--minute-angle': `${handAngles.value.minute}deg`,
  }
})

const displayText = computed(() => parsedTime.value?.text ?? '--:--')
</script>

<template>
  <span class="slot-time-clock" :style="clockStyle" :aria-label="displayText">
    <span class="clock-flip" role="img" :aria-label="displayText">
      <span class="clock-face analog-face">
        <span class="dial-ring"></span>
        <span class="dial-center"></span>
        <span class="hand hand-hour"></span>
        <span class="hand hand-minute"></span>
      </span>
      <span class="clock-face digital-face">
        <span class="digital-window">{{ displayText }}</span>
      </span>
    </span>
  </span>
</template>

<style scoped>
.slot-time-clock {
  --clock-size: 20px;
  --hour-angle: 0deg;
  --minute-angle: 0deg;
  display: inline-flex;
  width: var(--clock-size);
  height: var(--clock-size);
}

.clock-flip {
  width: 100%;
  height: 100%;
  position: relative;
  transform-style: preserve-3d;
  transition: transform 280ms ease;
}

.slot-time-clock:hover .clock-flip {
  transform: rotateY(180deg);
}

.clock-face {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  backface-visibility: hidden;
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

.digital-face {
  transform: rotateY(180deg);
  border-radius: 6px;
  background: linear-gradient(180deg, #e9f4ff 0%, #d4e7ff 100%);
  box-shadow: inset 0 0 0 1px rgba(31, 95, 212, 0.4);
}

.digital-window {
  color: #13325f;
  font-size: calc(var(--clock-size) * 0.33);
  line-height: 1;
  font-weight: 700;
  letter-spacing: 0.03em;
  font-family: 'Courier Prime', 'Courier New', monospace;
  font-variant-numeric: tabular-nums;
  text-shadow: 0 0 8px rgba(52, 112, 196, 0.34);
}
</style>

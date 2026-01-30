<template>
  <div
    ref="rootRef"
    class="reticulum-root scanlines grid-bg hex-pattern"
    :style="rootStyle"
  >
    <div class="reticulum-scanline">
      <div class="reticulum-scanline-bar" />
    </div>

    <div class="reticulum-corner reticulum-corner--tl" />
    <div class="reticulum-corner reticulum-corner--tr" />
    <div class="reticulum-corner reticulum-corner--bl" />
    <div class="reticulum-corner reticulum-corner--br" />

    <div ref="containerRef" class="reticulum-container" :style="containerStyle">
      <div class="reticulum-header">
        <h1 class="reticulum-title glow-text">LOCAL INFO</h1>
        <div class="reticulum-title-line" />
      </div>

      <div class="reticulum-clock">
        <div class="reticulum-ring reticulum-ring--outer">
          <svg width="320" height="320" class="reticulum-ring-svg">
            <circle
              cx="160"
              cy="160"
              r="155"
              fill="none"
              stroke="#00ffff"
              stroke-width="1"
              stroke-dasharray="10 20 5 15"
            />
          </svg>
        </div>

        <svg width="320" height="320" class="reticulum-ring reticulum-ring--markers">
          <line
            v-for="i in 60"
            :key="i"
            :x1="160 + 130 * Math.cos(((i - 1) * 6) * Math.PI / 180)"
            :y1="160 + 130 * Math.sin(((i - 1) * 6) * Math.PI / 180)"
            :x2="160 + ((i - 1) % 5 === 0 ? 120 : 125) * Math.cos(((i - 1) * 6) * Math.PI / 180)"
            :y2="160 + ((i - 1) % 5 === 0 ? 120 : 125) * Math.sin(((i - 1) * 6) * Math.PI / 180)"
            stroke="#00ffff"
            :stroke-width="(i - 1) % 5 === 0 ? 2 : 1"
            :opacity="(i - 1) % 5 === 0 ? 0.8 : 0.4"
          />
        </svg>

        <svg width="320" height="320" class="reticulum-ring progress-ring">
          <circle
            stroke="rgba(0, 255, 255, 0.2)"
            :stroke-width="strokeWidth"
            fill="transparent"
            :r="normalizedRadius"
            cx="160"
            cy="160"
          />
          <circle
            stroke="#00ffff"
            :stroke-width="strokeWidth"
            fill="transparent"
            :r="normalizedRadius"
            cx="160"
            cy="160"
            :stroke-dasharray="`${circumference} ${circumference}`"
            :style="{ strokeDashoffset }"
            class="progress-ring-circle"
            stroke-linecap="round"
          />
        </svg>

        <svg width="320" height="320" class="reticulum-ring reticulum-ring--inner">
          <circle
            cx="160"
            cy="160"
            r="100"
            fill="none"
            stroke="url(#gradient)"
            stroke-width="2"
            opacity="0.6"
          />
          <defs>
            <linearGradient id="gradient" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stop-color="#00ffff" stop-opacity="0" />
              <stop offset="50%" stop-color="#00ffff" stop-opacity="1" />
              <stop offset="100%" stop-color="#00ffff" stop-opacity="0" />
            </linearGradient>
          </defs>
        </svg>

        <div class="reticulum-clock-face">
          <div class="reticulum-time">
            <div class="reticulum-time-main">
              <span class="reticulum-time-hours glow-text">{{ time.hours }}</span>
              <span class="reticulum-time-sep animate-blink">:</span>
              <span class="reticulum-time-minutes glow-text">{{ time.minutes }}</span>
            </div>
            <div class="reticulum-time-sub">
              <span class="reticulum-time-seconds">{{ time.seconds }}</span>
              <span class="reticulum-time-ampm">{{ time.ampm }}</span>
            </div>
          </div>
        </div>

        <div class="reticulum-indicator">
          <div class="reticulum-indicator-triangle" />
        </div>
      </div>

      <div class="reticulum-panels">
        <div class="reticulum-panel glass-panel">
          <div class="reticulum-panel-corner reticulum-panel-corner--tl" />
          <div class="reticulum-panel-corner reticulum-panel-corner--tr" />
          <div class="reticulum-panel-corner reticulum-panel-corner--bl" />
          <div class="reticulum-panel-corner reticulum-panel-corner--br" />

          <div class="reticulum-panel-content">
            <div>
              <p class="reticulum-panel-label">
                {{ weather.loading ? "LOCATING..." : weather.location }}
              </p>
              <div class="reticulum-weather">
                <span v-if="weather.loading" class="reticulum-weather-loading">--</span>
                <span v-else-if="weather.error" class="reticulum-weather-error">{{ weather.error }}</span>
                <template v-else>
                  <span class="reticulum-weather-temp glow-text">{{ weather.temperature }}</span>
                  <span class="reticulum-weather-unit">°C</span>
                </template>
              </div>
            </div>

            <div v-if="!weather.loading && !weather.error" class="reticulum-temp-scale">
              <div
                v-for="(temp, idx) in tempScale"
                :key="temp"
                :class="weather.temperature >= temp ? 'reticulum-temp-bar reticulum-temp-bar--active' : 'reticulum-temp-bar'"
                :style="{ width: `${32 - idx * 2}px` }"
              />
            </div>
          </div>

          <div class="reticulum-refresh">
            <div
              :class="weather.loading
                ? 'reticulum-refresh-dot reticulum-refresh-dot--loading'
                : 'reticulum-refresh-dot'"
            />
          </div>
        </div>

        <div class="reticulum-panel glass-panel">
          <div class="reticulum-panel-corner reticulum-panel-corner--tl" />
          <div class="reticulum-panel-corner reticulum-panel-corner--tr" />
          <div class="reticulum-panel-corner reticulum-panel-corner--bl" />
          <div class="reticulum-panel-corner reticulum-panel-corner--br" />

          <div class="reticulum-panel-content reticulum-panel-content--calendar">
            <div>
              <p class="reticulum-panel-label">{{ calendar.month }} {{ calendar.year }}</p>
              <p class="reticulum-panel-sub">{{ calendar.weekday }}</p>
            </div>
            <div class="reticulum-calendar-day glow-text">
              {{ String(calendar.day).padStart(2, '0') }}
            </div>
          </div>
        </div>
      </div>

      <div class="reticulum-status">
        <div class="reticulum-status-item">
          <div class="reticulum-status-dot animate-pulse-glow" />
          <span class="reticulum-status-text">SYSTEM ONLINE</span>
        </div>
        <div class="reticulum-status-divider" />
        <div class="reticulum-status-item">
          <svg
            class="reticulum-status-icon"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"
            />
          </svg>
          <span class="reticulum-status-text">100%</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import "./ReticulumClock.css";

type WeatherData = {
  temperature: number;
  location: string;
  loading: boolean;
  error: string | null;
};

type TimeData = {
  hours: string;
  minutes: string;
  seconds: string;
  ampm: string;
};

type CalendarData = {
  day: number;
  month: string;
  year: number;
  weekday: string;
};

const props = withDefaults(
  defineProps<{
    width?: string;
    height?: string;
    background?: string;
    padding?: string;
    scale?: number;
    autoScale?: boolean;
    minScale?: number;
    maxScale?: number;
  }>(),
  {
    width: "100%",
    height: "100%",
    background: "radial-gradient(ellipse at center, #0a1f24 0%, #02080a 100%)",
    padding: "16px",
    scale: 1,
    autoScale: true,
    minScale: 0.6,
    maxScale: 1,
  },
);

const rootRef = ref<HTMLElement | null>(null);
const containerRef = ref<HTMLElement | null>(null);
const scaleValue = ref(props.scale);

const rootStyle = computed(() => ({
  width: props.width,
  height: props.height,
  background: props.background,
  padding: props.padding,
}));

const containerStyle = computed(() => ({
  transform: `scale(${scaleValue.value})`,
  transformOrigin: "center",
}));

const updateScale = () => {
  if (!props.autoScale) {
    scaleValue.value = props.scale;
    return;
  }
  const rootEl = rootRef.value;
  const containerEl = containerRef.value;
  if (!rootEl || !containerEl) return;

  const availableW = rootEl.clientWidth;
  const availableH = rootEl.clientHeight;
  const baseW = containerEl.scrollWidth;
  const baseH = containerEl.scrollHeight;

  if (baseW === 0 || baseH === 0) return;

  const nextScale = Math.min(availableW / baseW, availableH / baseH);
  const clamped = Math.min(props.maxScale, Math.max(props.minScale, nextScale));
  scaleValue.value = clamped;
};

const time = reactive<TimeData>({
  hours: "12",
  minutes: "00",
  seconds: "00",
  ampm: "AM",
});

const calendar = reactive<CalendarData>({
  day: 1,
  month: "JANUARY",
  year: 2024,
  weekday: "MONDAY",
});

const weather = reactive<WeatherData>({
  temperature: 0,
  location: "LOCATING...",
  loading: true,
  error: null,
});

const secondsProgress = ref(0);
const radius = 140;
const strokeWidth = 4;
const normalizedRadius = radius - strokeWidth * 2;
const circumference = normalizedRadius * 2 * Math.PI;

const strokeDashoffset = computed(() =>
  circumference - (secondsProgress.value / 100) * circumference,
);

const tempScale = [40, 35, 30, 25, 20, 15, 10, 5, 0, -5];

const updateTime = () => {
  const now = new Date();
  let hours = now.getHours();
  const ampm = hours >= 12 ? "PM" : "AM";
  hours = hours % 12;
  hours = hours || 12;

  time.hours = hours.toString().padStart(2, "0");
  time.minutes = now.getMinutes().toString().padStart(2, "0");
  time.seconds = now.getSeconds().toString().padStart(2, "0");
  time.ampm = ampm;

  secondsProgress.value = (now.getSeconds() / 60) * 100;
};

const updateCalendar = () => {
  const now = new Date();
  const months = [
    "JANUARY",
    "FEBRUARY",
    "MARCH",
    "APRIL",
    "MAY",
    "JUNE",
    "JULY",
    "AUGUST",
    "SEPTEMBER",
    "OCTOBER",
    "NOVEMBER",
    "DECEMBER",
  ];
  const weekdays = [
    "SUNDAY",
    "MONDAY",
    "TUESDAY",
    "WEDNESDAY",
    "THURSDAY",
    "FRIDAY",
    "SATURDAY",
  ];

  calendar.day = now.getDate();
  calendar.month = months[now.getMonth()];
  calendar.year = now.getFullYear();
  calendar.weekday = weekdays[now.getDay()];
};

const fetchWeather = async (latitude: number, longitude: number) => {
  try {
    const weatherResponse = await fetch(
      `https://api.open-meteo.com/v1/forecast?latitude=${latitude}&longitude=${longitude}&current_weather=true`,
    );

    if (!weatherResponse.ok) {
      throw new Error("Failed to fetch weather data");
    }

    const weatherData = await weatherResponse.json();

    let locationName = "UNKNOWN LOCATION";
    try {
      const geoResponse = await fetch(
        `https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=${latitude}&longitude=${longitude}&localityLanguage=en`,
      );
      if (geoResponse.ok) {
        const geoData = await geoResponse.json();
        locationName =
          geoData.city ||
          geoData.locality ||
          geoData.principalSubdivision ||
          "UNKNOWN LOCATION";
      }
    } catch {
      locationName = `${latitude.toFixed(2)}\u00b0N, ${longitude.toFixed(2)}\u00b0E`;
    }

    weather.temperature = Math.round(weatherData.current_weather.temperature);
    weather.location = locationName.toUpperCase();
    weather.loading = false;
    weather.error = null;
  } catch {
    weather.loading = false;
    weather.error = "UNABLE TO FETCH WEATHER DATA";
  }
};

const getLocation = () => {
  if (!navigator.geolocation) {
    weather.loading = false;
    weather.error = "GEOLOCATION NOT SUPPORTED";
    return;
  }

  navigator.geolocation.getCurrentPosition(
    (position) => {
      fetchWeather(position.coords.latitude, position.coords.longitude);
    },
    (error) => {
      let errorMsg = "LOCATION ACCESS DENIED";
      if (error.code === error.TIMEOUT) {
        errorMsg = "LOCATION TIMEOUT";
      } else if (error.code === error.POSITION_UNAVAILABLE) {
        errorMsg = "POSITION UNAVAILABLE";
      }
      weather.temperature = 0;
      weather.location = "LOCATION ERROR";
      weather.loading = false;
      weather.error = errorMsg;
    },
    {
      enableHighAccuracy: true,
      timeout: 10000,
      maximumAge: 0,
    },
  );
};

let timeInterval: number | undefined;
let calendarInterval: number | undefined;
let weatherInterval: number | undefined;
let resizeObserver: ResizeObserver | undefined;

onMounted(() => {
  updateTime();
  updateCalendar();
  getLocation();

  timeInterval = window.setInterval(updateTime, 1000);
  calendarInterval = window.setInterval(updateCalendar, 60000);
  weatherInterval = window.setInterval(getLocation, 600000);

  nextTick(() => {
    updateScale();
    if (rootRef.value) {
      resizeObserver = new ResizeObserver(updateScale);
      resizeObserver.observe(rootRef.value);
    }
    if (containerRef.value && resizeObserver) {
      resizeObserver.observe(containerRef.value);
    }
  });
});

onBeforeUnmount(() => {
  if (timeInterval) window.clearInterval(timeInterval);
  if (calendarInterval) window.clearInterval(calendarInterval);
  if (weatherInterval) window.clearInterval(weatherInterval);
  if (resizeObserver) resizeObserver.disconnect();
});

watch(
  () => [props.width, props.height, props.padding, props.scale, props.autoScale],
  () => {
    nextTick(updateScale);
  },
);
</script>

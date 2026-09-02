#!/usr/bin/env bash
set -eu

interval=2
count=0

usage() {
  echo "Usage: $0 [--interval SECONDS] [--count SAMPLES]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --interval)
      interval="${2:-}"
      shift 2
      ;;
    --count)
      count="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

if ! [[ "${interval}" =~ ^[0-9]+([.][0-9]+)?$ ]] || [[ "${interval}" == "0" ]]; then
  echo "--interval must be a positive number" >&2
  exit 2
fi
if ! [[ "${count}" =~ ^[0-9]+$ ]]; then
  echo "--count must be a non-negative integer" >&2
  exit 2
fi
if [[ ! -r /proc/stat || ! -r /proc/meminfo ]]; then
  echo "This monitor requires Linux /proc (run it on the Raspberry Pi)." >&2
  exit 1
fi

read_cpu() {
  awk '/^cpu / {
    idle = $5 + $6
    total = 0
    for (i = 2; i <= NF; i++) total += $i
    print total, idle
    exit
  }' /proc/stat
}

read_memory() {
  awk '
    /^MemTotal:/ { total = $2 }
    /^MemAvailable:/ { available = $2 }
    END {
      used = total - available
      printf "%.1f %.1f %.1f\n", used * 100 / total, used / 1024, total / 1024
    }
  ' /proc/meminfo
}

read_temperature() {
  if [[ -r /sys/class/thermal/thermal_zone0/temp ]]; then
    awk '{printf "%.1f", $1 / 1000}' /sys/class/thermal/thermal_zone0/temp
  elif command -v vcgencmd >/dev/null 2>&1; then
    vcgencmd measure_temp 2>/dev/null | sed -n "s/.*=\([0-9.]*\).*/\1/p"
  else
    printf 'n/a'
  fi
}

read -r previous_total previous_idle < <(read_cpu)

samples=0
while [[ "${count}" -eq 0 || "${samples}" -lt "${count}" ]]; do
  sleep "${interval}"
  read -r current_total current_idle < <(read_cpu)
  read -r memory_pct memory_mib total_mib < <(read_memory)

  total_delta=$((current_total - previous_total))
  idle_delta=$((current_idle - previous_idle))
  cpu_pct="$(awk -v total="${total_delta}" -v idle="${idle_delta}" \
    'BEGIN { if (total <= 0) print "0.0"; else printf "%.1f", (total - idle) * 100 / total }')"

  printf '\n## %s\n' "$(date '+%Y-%m-%d %H:%M:%S')"
  printf 'cpu_usage_pct=%s memory_usage_pct=%s memory_used_mib=%s memory_total_mib=%s cpu_temp_c=%s\n' \
    "${cpu_pct}" "${memory_pct}" "${memory_mib}" "${total_mib}" "$(read_temperature)"

  echo '-- uptime / load average --'
  uptime 2>&1 || true

  echo '-- memory --'
  if command -v free >/dev/null 2>&1; then
    free -h 2>&1 || true
  else
    echo 'free=not-available'
  fi

  echo '-- top CPU processes --'
  if command -v ps >/dev/null 2>&1; then
    ps -eo pid,comm,%cpu,%mem --sort=-%cpu 2>&1 | sed -n '1,6p'
  else
    echo 'ps=not-available'
  fi

  echo '-- Raspberry Pi temperature --'
  if command -v vcgencmd >/dev/null 2>&1; then
    vcgencmd measure_temp 2>&1 || true
  else
    echo 'vcgencmd=not-available'
  fi

  echo '-- Raspberry Pi throttling --'
  if command -v vcgencmd >/dev/null 2>&1; then
    vcgencmd get_throttled 2>&1 || true
  else
    echo 'vcgencmd=not-available'
  fi

  previous_total="${current_total}"
  previous_idle="${current_idle}"
  samples=$((samples + 1))
done

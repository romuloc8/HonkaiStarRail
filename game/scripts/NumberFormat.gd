class_name NumberFormat
## 大数与时长格式化工具。

const UNITS := ["", "K", "M", "B", "T", "Qa", "Qi"]


## 1234 -> "1.2K"，5600000 -> "5.6M"，小于 1000 显示整数。
static func format(value: float, decimals: int = 1) -> String:
	if is_nan(value) or is_inf(value):
		return "∞"
	var negative := value < 0.0
	var abs_value := absf(value)
	if abs_value < 1000.0:
		var text := str(int(floorf(abs_value)))
		return ("-" + text) if negative else text
	var unit_index := 0
	while abs_value >= 1000.0 and unit_index < UNITS.size() - 1:
		abs_value /= 1000.0
		unit_index += 1
	var body := ("%." + str(decimals) + "f") % abs_value
	# 去掉多余的 .0
	if body.ends_with(".0"):
		body = body.substr(0, body.length() - 2)
	return ("-" if negative else "") + body + UNITS[unit_index]


## 每秒产出显示："+1.2K/秒"
static func format_rate(value: float) -> String:
	if absf(value) < 1000.0:
		return "%.1f/秒" % value
	return format(value) + "/秒"


## 3725 -> "1小时2分5秒"，65 -> "1分5秒"，9 -> "9秒"
static func format_duration(seconds: float) -> String:
	var total := int(ceilf(maxf(seconds, 0.0)))
	var h := total / 3600
	var m := (total % 3600) / 60
	var s := total % 60
	var parts: Array[String] = []
	if h > 0:
		parts.append("%d小时" % h)
	if m > 0:
		parts.append("%d分" % m)
	if s > 0 or parts.is_empty():
		parts.append("%d秒" % s)
	return "".join(parts)


## 65 -> "01:05"，3725 -> "1:02:05"
static func format_clock(seconds: float) -> String:
	var total := int(ceilf(maxf(seconds, 0.0)))
	var h := total / 3600
	var m := (total % 3600) / 60
	var s := total % 60
	if h > 0:
		return "%d:%02d:%02d" % [h, m, s]
	return "%02d:%02d" % [m, s]


## 0.15 -> "+15%"
static func format_percent(value: float) -> String:
	var pct := value * 100.0
	var text := ("%.0f" % pct) if is_equal_approx(pct, roundf(pct)) else ("%.1f" % pct)
	return ("+" if value >= 0.0 else "") + text + "%"

from org.csstudio.display.builder.model.properties import WidgetColor
from org.csstudio.opibuilder.scriptUtil import PVUtil

currentTemp = PVUtil.getDouble(pvs[0])
hihiRaw = PVUtil.getDouble(pvs[1])
highRaw = PVUtil.getDouble(pvs[2])


widget.setPropertyValue("level_hihi", hihiRaw)
if highRaw == 0:
    widget.setPropertyValue("level_high", hihiRaw)
else:
    widget.setPropertyValue("level_high", highRaw)

alpha = 200

if currentTemp < hihiRaw:
    widget.setPropertyValue("colors.needle_color", WidgetColor(96, 255, 96, alpha))

if currentTemp >= hihiRaw * 0.75:
    widget.setPropertyValue("colors.needle_color", WidgetColor(255, 241, 0, alpha))

if currentTemp >= hihiRaw:
    widget.setPropertyValue("colors.needle_color", WidgetColor(255, 0, 0, alpha))

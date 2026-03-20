# Mobile Responsive - #511 (15 RTC)
def responsive(width):
  if width < 768: return 'mobile'
  elif width < 1024: return 'tablet'
  else: return 'desktop'

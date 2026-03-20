# Activity Feed - #512 (20 RTC)
class ActivityFeed:
  def add(s, u, action, target): return {'user': u, 'action': action, 'target': target}
  def get(s, u): return {'user': u, 'activities': []}

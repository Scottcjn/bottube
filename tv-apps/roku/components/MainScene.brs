sub init()
  m.list = m.top.findNode("trending")
  m.video = m.top.findNode("video")
  loadTrending()
end sub

sub loadTrending()
  t = CreateObject("roSGNode", "Task")
  t.observeField("content", "onTrending")
  t.control = "RUN"
  ' placeholder: production app should call /api/trending and map rows
end sub

sub onTrending()
  ' TODO: bind feed rows for remote navigation playback
end sub

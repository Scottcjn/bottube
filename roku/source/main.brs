sub Main()
    screen = CreateObject("roSGScreen")
    m.port = CreateObject("roMessagePort")
    screen.setMessagePort(m.port)
    
    scene = screen.CreateScene("MainScene")
    screen.show()
    
    while true
        msg = wait(0, m.port)
        msgType = type(msg)
        
        if msgType = "roSGScreenEvent"
            if msg.isScreenClosed() then return
        end if
    end while
end sub

sub init()
    m.top.setFocus(true)
    
    m.api = CreateObject("roSGNode", "ApiService")
    m.api.baseUrl = "http://localhost:5001/api"
    
    setupUI()
    loadTrendingVideos()
end sub

sub setupUI()
    m.background = m.top.createChild("Rectangle")
    m.background.width = 1920
    m.background.height = 1080
    m.background.color = "0x1a1a1aFF"
    
    m.header = m.top.createChild("Group")
    m.header.translation = [60, 40]
    
    m.logo = m.header.createChild("Label")
    m.logo.text = "BoTTube"
    m.logo.font.size = 48
    m.logo.color = "0xFFFFFFFF"
    
    m.navBar = m.top.createChild("RowList")
    m.navBar.translation = [60, 120]
    m.navBar.itemComponentName = "NavItem"
    m.navBar.numRows = 1
    m.navBar.rowFocusAnimationStyle = "floatingFocus"
    
    navContent = CreateObject("roSGNode", "ContentNode")
    navItem1 = navContent.createChild("ContentNode")
    navItem1.title = "Trending"
    navItem2 = navContent.createChild("ContentNode")
    navItem2.title = "Recent"
    navItem3 = navContent.createChild("ContentNode")
    navItem3.title = "Categories"
    m.navBar.content = navContent
    
    m.videoGrid = m.top.createChild("RowList")
    m.videoGrid.translation = [60, 200]
    m.videoGrid.itemSize = [400, 280]
    m.videoGrid.numRows = 3
    m.videoGrid.rowItemSize = [400, 240]
    m.videoGrid.itemComponentName = "VideoTile"
    m.videoGrid.rowFocusAnimationStyle = "floatingFocus"
    
    m.navBar.observeField("itemSelected", "onNavSelected")
    m.videoGrid.observeField("itemSelected", "onVideoSelected")
end sub

sub loadTrendingVideos()
    ' Implementation for loading trending videos
    print "Loading trending videos..."
end sub

sub onNavSelected()
    ' Handle navigation selection
    print "Navigation item selected"
end sub

sub onVideoSelected()
    ' Handle video selection
    print "Video selected"
end sub
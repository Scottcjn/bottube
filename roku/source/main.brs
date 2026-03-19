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
    request = CreateObject("roUrlTransfer")
    request.setUrl(m.api.baseUrl + "/videos/trending")
    request.setMessagePort(m.port)
    
    if request.asyncGetToString()
        m.loadingTrending = true
    end if
end sub

sub loadRecentVideos()
    request = CreateObject("roUrlTransfer")
    request.setUrl(m.api.baseUrl + "/videos/recent")
    request.setMessagePort(m.port)
    
    if request.asyncGetToString()
        m.loadingRecent = true
    end if
end sub

sub onNavSelected(event as Object)
    selectedIndex = event.getRoSGNode().itemSelected
    
    if selectedIndex = 0
        loadTrendingVideos()
    else if selectedIndex = 1
        loadRecentVideos()
    else if selectedIndex = 2
        showCategories()
    end if
end sub

sub onVideoSelected(event as Object)
    grid = event.getRoSGNode()
    selectedItem = grid.content.getChild(grid.rowItemSelected[0]).getChild(grid.rowItemSelected[1])
    
    videoId = selectedItem.videoId
    playVideo(videoId)
end sub

sub playVideo(videoId as String)
    videoPlayer = CreateObject("roSGNode", "Video")
    videoPlayer.content = CreateObject("roSGNode", "ContentNode")
    videoPlayer.content.url = m.api.baseUrl + "/videos/" + videoId + "/stream"
    videoPlayer.content.title = "BoTTube Video"
    videoPlayer.content.streamFormat = "mp4"
    
    videoPlayer.visible = true
    videoPlayer.control = "play"
    m.top.appendChild(videoPlayer)
    
    videoPlayer.observeField("state", "onVideoStateChanged")
end sub

sub onVideoStateChanged(event as Object)
    video = event.getRoSGNode()
    
    if video.state = "finished" or video.state = "stopped"
        video.visible = false
        m.top.removeChild(video)
        m.videoGrid.setFocus(true)
    end if
end sub

sub showCategories()
    categoryContent = CreateObject("roSGNode", "ContentNode")
    
    cat1 = categoryContent.createChild("ContentNode")
    cat1.title = "Tech"
    cat2 = categoryContent.createChild("ContentNode") 
    cat2.title = "Gaming"
    cat3 = categoryContent.createChild("ContentNode")
    cat3.title = "Music"
    
    m.videoGrid.content = categoryContent
end sub

function onKeyEvent(key as String, press as Boolean) as Boolean
    if press
        if key = "back"
            return true
        else if key = "up" or key = "down" or key = "left" or key = "right"
            return false
        end if
    end if
    
    return false
end function

sub handleApiResponse(msg as Object)
    if m.loadingTrending
        m.loadingTrending = false
        parseVideoResponse(msg.getString(), "trending")
    else if m.loadingRecent
        m.loadingRecent = false
        parseVideoResponse(msg.getString(), "recent")
    end if
end sub

sub parseVideoResponse(responseStr as String, contentType as String)
    json = ParseJson(responseStr)
    
    if json <> Invalid and json.videos <> Invalid
        content = CreateObject("roSGNode", "ContentNode")
        
        for each video in json.videos
            videoNode = content.createChild("ContentNode")
            videoNode.title = video.title
            videoNode.description = video.description
            videoNode.videoId = video.id
            
            if video.thumbnail <> Invalid
                videoNode.hdPosterUrl = video.thumbnail
            end if
        end for
        
        m.videoGrid.content = content
    end if
end sub
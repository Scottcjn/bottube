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
    request.SetUrl(m.api.baseUrl + "/tv/videos/trending")
    request.SetRequest("GET")
    response = request.GetToString()
    
    if response <> ""
        json = ParseJson(response)
        if json <> invalid and json.videos <> invalid
            populateVideoGrid(json.videos)
        end if
    end if
end sub

sub populateVideoGrid(videos as object)
    content = CreateObject("roSGNode", "ContentNode")
    
    for each video in videos
        videoNode = content.createChild("ContentNode")
        videoNode.title = video.title
        videoNode.description = video.description
        videoNode.hdPosterUrl = video.thumbnail_url
        videoNode.id = video.id
        videoNode.username = video.username
        videoNode.viewCount = video.view_count
    end for
    
    m.videoGrid.content = content
end sub

sub onNavSelected()
    selectedIndex = m.navBar.itemSelected
    
    if selectedIndex = 0
        loadTrendingVideos()
    else if selectedIndex = 1
        loadRecentVideos()
    else if selectedIndex = 2
        loadCategories()
    end if
end sub

sub loadRecentVideos()
    request = CreateObject("roUrlTransfer")
    request.SetUrl(m.api.baseUrl + "/tv/videos/recent")
    request.SetRequest("GET")
    response = request.GetToString()
    
    if response <> ""
        json = ParseJson(response)
        if json <> invalid and json.videos <> invalid
            populateVideoGrid(json.videos)
        end if
    end if
end sub

sub loadCategories()
    ' Placeholder for categories functionality
    print "Categories not implemented yet"
end sub

sub onVideoSelected()
    selectedVideo = m.videoGrid.content.getChild(m.videoGrid.itemSelected)
    
    if selectedVideo <> invalid
        playVideo(selectedVideo.id)
    end if
end sub

sub playVideo(videoId as integer)
    request = CreateObject("roUrlTransfer")
    request.SetUrl(m.api.baseUrl + "/tv/video/" + videoId.toStr())
    request.SetRequest("GET")
    response = request.GetToString()
    
    if response <> ""
        json = ParseJson(response)
        if json <> invalid and json.stream_url <> invalid
            video = CreateObject("roVideoScreen")
            port = CreateObject("roMessagePort")
            video.SetMessagePort(port)
            
            videoContent = {
                stream: { url: json.stream_url },
                title: json.title,
                description: json.description
            }
            
            video.SetContent(videoContent)
            video.show()
            
            while true
                msg = wait(0, port)
                if type(msg) = "roVideoScreenEvent"
                    if msg.isScreenClosed()
                        exit while
                    end if
                end if
            end while
        end if
    end if
end sub
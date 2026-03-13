
document.addEventListener('keydown', function(e) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    const video = document.querySelector('video');
    if (!video) return;
    switch(e.key.toLowerCase()) {
        case 'k': case ' ': e.preventDefault(); video.paused ? video.play() : video.pause(); break;
        case 'f': e.preventDefault(); document.fullscreenElement ? document.exitFullscreen() : video.requestFullscreen(); break;
        case 'm': video.muted = !video.muted; break;
    }
});
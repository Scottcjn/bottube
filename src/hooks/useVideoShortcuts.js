import { useEffect } from 'react';

/**
 * Custom hook to handle keyboard shortcuts for video playback.
 * Supports Accessibility (A11y) requirements.
 * 
 * Shortcuts:
 * - Space / K: Play/Pause
 * - J: Rewind 10s
 * - L: Forward 10s
 * - F: Fullscreen
 * - M: Mute
 * 
 * @param {React.RefObject} videoRef - Ref to the video element
 */
const useVideoShortcuts = (videoRef) => {
  useEffect(() => {
    const handleKeyDown = (event) => {
      const video = videoRef.current;
      if (!video) return;

      // Ignore shortcuts if user is typing in an input field
      const tagName = document.activeElement.tagName.toLowerCase();
      if (tagName === 'input' || tagName === 'textarea') {
        return;
      }

      const key = event.key.toLowerCase();

      switch (key) {
        case ' ':
        case 'k':
          event.preventDefault(); // Prevent scrolling with Space
          if (video.paused) {
            video.play();
          } else {
            video.pause();
          }
          break;
        
        case 'j':
          event.preventDefault();
          video.currentTime = Math.max(0, video.currentTime - 10);
          break;
        
        case 'l':
          event.preventDefault();
          video.currentTime = Math.min(video.duration, video.currentTime + 10);
          break;
        
        case 'f':
          event.preventDefault();
          if (document.fullscreenElement) {
            document.exitFullscreen();
          } else {
            video.requestFullscreen().catch(err => {
              console.error(`Error attempting to enable fullscreen: ${err.message}`);
            });
          }
          break;
        
        case 'm':
          event.preventDefault();
          video.muted = !video.muted;
          break;
        
        default:
          break;
      }
    };

    window.addEventListener('keydown', handleKeyDown);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [videoRef]);
};

export default useVideoShortcuts;

import React, { useRef } from 'react';
import useVideoShortcuts from '../hooks/useVideoShortcuts';

/**
 * BoTTube Accessible Video Player Component
 * Implements keyboard shortcuts for better usability.
 */
const VideoPlayer = ({ src, poster }) => {
  const videoRef = useRef(null);

  // Initialize keyboard shortcuts
  useVideoShortcuts(videoRef);

  return (
    <div className="video-wrapper" style={{ position: 'relative', outline: 'none' }}>
      <video
        ref={videoRef}
        src={src}
        poster={poster}
        controls
        width="100%"
        // Ensure the video container can be focused if needed, 
        // though the hook listens to window events.
        tabIndex="-1" 
      >
        Your browser does not support the video tag.
      </video>
      {/* Optional: Visual overlay for shortcut hints can be added here */}
    </div>
  );
};

export default VideoPlayer;

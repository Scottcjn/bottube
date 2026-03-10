/**
 * Video Detail Hook
 * Fetches and manages single video data
 */

import { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';
import { Video, Comment } from '../types/api';

interface UseVideoDetailResult {
  video: Video | null;
  comments: Comment[];
  isLoading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  vote: (value: 1 | -1) => Promise<void>;
  addComment: (content: string) => Promise<void>;
  streamUrl: string | null;
  thumbnailUrl: string | null;
}

export function useVideoDetail(videoId: string | null): UseVideoDetailResult {
  const [video, setVideo] = useState<Video | null>(null);
  const [comments, setComments] = useState<Comment[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isVoting, setIsVoting] = useState(false);
  const [isAddingComment, setIsAddingComment] = useState(false);

  const fetchVideo = useCallback(async () => {
    if (!videoId) {
      setVideo(null);
      setComments([]);
      setIsLoading(false);
      return;
    }

    try {
      setIsLoading(true);
      setError(null);

      const [videoData, commentsData] = await Promise.all([
        api.getVideo(videoId),
        api.getComments(videoId),
      ]);

      setVideo(videoData);
      setComments(commentsData);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load video';
      setError(message);
      setVideo(null);
      setComments([]);
    } finally {
      setIsLoading(false);
    }
  }, [videoId]);

  const refresh = useCallback(async () => {
    await fetchVideo();
  }, [fetchVideo]);

  const vote = useCallback(async (value: 1 | -1) => {
    if (!videoId || isVoting) return;

    setIsVoting(true);
    const previousVideo = video;

    try {
      // Optimistically update local state
      setVideo(prev => prev ? {
        ...prev,
        likes: value === 1 ? prev.likes + 1 : prev.likes,
        dislikes: value === -1 ? prev.dislikes + 1 : prev.dislikes,
      } : null);

      await api.vote(videoId, { vote: value });
    } catch (err) {
      // Revert on error
      setVideo(previousVideo);
      console.error('Vote failed:', err);
      throw err;
    } finally {
      setIsVoting(false);
    }
  }, [videoId, isVoting, video]);

  const addComment = useCallback(async (content: string) => {
    if (!videoId || isAddingComment) return;

    setIsAddingComment(true);

    try {
      const newComment = await api.addComment(videoId, { content });
      setComments(prev => [newComment, ...prev]);
    } catch (err) {
      console.error('Comment failed:', err);
      throw err;
    } finally {
      setIsAddingComment(false);
    }
  }, [videoId, isAddingComment]);

  useEffect(() => {
    fetchVideo();
  }, [videoId]); // eslint-disable-line react-hooks/exhaustive-deps

  const streamUrl = videoId ? api.getVideoStreamUrl(videoId) : null;
  const thumbnailUrl = videoId ? api.getThumbnailUrl(videoId) : null;

  return {
    video,
    comments,
    isLoading,
    error,
    refresh,
    vote,
    addComment,
    streamUrl,
    thumbnailUrl,
  };
}

/**
 * Video Feed Hook
 * Fetches and manages video feed data
 */

import { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';
import { Video } from '../types/api';

interface UseFeedResult {
  videos: Video[];
  isLoading: boolean;
  isRefreshing: boolean;
  isLoadingMore: boolean;
  hasMore: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  loadMore: () => Promise<void>;
}

export function useFeed(feedType: 'feed' | 'trending' | 'videos' = 'feed'): UseFeedResult {
  const [videos, setVideos] = useState<Video[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);

  const fetchVideos = useCallback(async (page: number, refresh = false) => {
    try {
      setError(null);

      let result;
      switch (feedType) {
        case 'trending':
          result = await api.getTrending({ page, per_page: 20 });
          break;
        case 'videos':
          result = await api.getVideos({ page, per_page: 20 });
          break;
        case 'feed':
        default:
          result = await api.getFeed({ page, per_page: 20 });
          break;
      }

      const newVideos = result.videos || [];

      if (refresh) {
        setVideos(newVideos);
      } else {
        setVideos(prev => {
          // Deduplicate videos by video_id
          const existingIds = new Set(prev.map(v => v.video_id));
          const uniqueNew = newVideos.filter(v => !existingIds.has(v.video_id));
          return [...prev, ...uniqueNew];
        });
      }

      setHasMore(newVideos.length === 20 && page < result.pages);
      setCurrentPage(page);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load videos';
      setError(message);
      if (refresh) {
        setVideos([]);
      }
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
      setIsLoadingMore(false);
    }
  }, [feedType]);

  const refresh = useCallback(async () => {
    setIsRefreshing(true);
    setCurrentPage(1);
    await fetchVideos(1, true);
  }, [fetchVideos]);

  const loadMore = useCallback(async () => {
    if (isLoadingMore || !hasMore) return;
    setIsLoadingMore(true);
    await fetchVideos(currentPage + 1, false);
  }, [currentPage, hasMore, isLoadingMore, fetchVideos]);

  useEffect(() => {
    setIsLoading(true);
    setVideos([]);
    setCurrentPage(1);
    setHasMore(true);
    fetchVideos(1, true);
  }, [feedType]); // eslint-disable-line react-hooks/exhaustive-deps

  return {
    videos,
    isLoading,
    isRefreshing,
    isLoadingMore,
    hasMore,
    error,
    refresh,
    loadMore,
  };
}

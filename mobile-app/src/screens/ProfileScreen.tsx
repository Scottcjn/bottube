/**
 * Profile Screen
 * Displays agent profile and stats
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Image,
  TextInput,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { useAuth } from '../hooks/useAuth';
import { useFeed } from '../hooks/useFeed';
import { Agent, Video } from '../types/api';
import { api } from '../api/client';

interface ProfileScreenProps {
  agentName?: string; // If not provided, shows current user's profile
  onVideoPress: (videoId: string) => void;
  onBack?: () => void;
}

interface VideoCardProps {
  video: Video;
  onPress: () => void;
}

function ProfileVideoCard({ video, onPress }: VideoCardProps) {
  const thumbnailUrl = api.getThumbnailUrl(video.video_id);

  const formatViews = (views: number): string => {
    if (views >= 1000000) return `${(views / 1000000).toFixed(1)}M`;
    if (views >= 1000) return `${(views / 1000).toFixed(1)}K`;
    return String(views);
  };

  return (
    <TouchableOpacity style={styles.videoCard} onPress={onPress} activeOpacity={0.7}>
      <View style={styles.videoThumbnailContainer}>
        <Image
          source={{ uri: thumbnailUrl }}
          style={styles.videoThumbnail}
          resizeMode="cover"
        />
        <View style={styles.videoDurationBadge}>
          <Text style={styles.videoDurationText}>{video.duration}s</Text>
        </View>
      </View>
      <Text style={styles.videoTitle} numberOfLines={2}>{video.title}</Text>
      <Text style={styles.videoViews}>{formatViews(video.views)} views</Text>
    </TouchableOpacity>
  );
}

export function ProfileScreen({
  agentName: propAgentName,
  onVideoPress,
  onBack,
}: ProfileScreenProps) {
  const { agent: currentAgent, logout } = useAuth();
  const [profile, setProfile] = useState<Agent | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [displayName, setDisplayName] = useState('');
  const [bio, setBio] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  // Determine if viewing own profile
  const isOwnProfile = !propAgentName || propAgentName === currentAgent?.agent_name;
  const viewAgentName = propAgentName || currentAgent?.agent_name;

  // Fetch profile
  useEffect(() => {
    let isMounted = true;

    const fetchProfile = async () => {
      if (!viewAgentName) {
        if (isMounted) {
          setIsLoading(false);
        }
        return;
      }

      try {
        if (isMounted) {
          setIsLoading(true);
          setError(null);
        }
        const data = await api.getAgentProfile(viewAgentName);
        if (isMounted) {
          setProfile(data);
          setDisplayName(data.display_name || '');
          setBio(data.bio || '');
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to load profile';
        if (isMounted) {
          setError(message);
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    };

    fetchProfile();

    return () => {
      isMounted = false;
    };
  }, [viewAgentName]);

  // Load videos from this agent - filter to only this agent's videos
  const { videos, isLoading: videosLoading } = useFeed('videos');
  const agentVideos = videos.filter(v => v.agent_name === viewAgentName);

  const handleSaveProfile = async () => {
    if (!displayName.trim()) {
      Alert.alert('Error', 'Display name cannot be empty');
      return;
    }

    setIsSaving(true);
    try {
      await api.updateProfile({
        display_name: displayName.trim(),
        bio: bio.trim(),
      });
      setIsEditing(false);
      // Refresh profile
      if (currentAgent) {
        const updated = await api.getMe();
        setProfile(updated);
      }
      Alert.alert('Success', 'Profile updated');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to update profile';
      Alert.alert('Error', message);
    } finally {
      setIsSaving(false);
    }
  };

  const handleLogout = () => {
    Alert.alert(
      'Logout',
      'Are you sure you want to logout?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Logout',
          style: 'destructive',
          onPress: async () => {
            await logout();
          },
        },
      ]
    );
  };

  if (isLoading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#ff4500" />
        <Text style={styles.loadingText}>Loading profile...</Text>
      </View>
    );
  }

  if (error || (!profile && !isOwnProfile)) {
    return (
      <View style={styles.errorContainer}>
        <Text style={styles.errorText}>⚠️ {error || 'Profile not found'}</Text>
        {onBack && (
          <TouchableOpacity style={styles.backButton} onPress={onBack}>
            <Text style={styles.backButtonText}>Go Back</Text>
          </TouchableOpacity>
        )}
      </View>
    );
  }

  const displayProfile = profile || currentAgent;

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.scrollContent}>
      {/* Header */}
      <View style={styles.header}>
        {onBack && (
          <TouchableOpacity style={styles.backButtonContainer} onPress={onBack}>
            <Text style={styles.backButtonText}>←</Text>
          </TouchableOpacity>
        )}
      </View>

      {/* Avatar */}
      <View style={styles.avatarContainer}>
        <Image
          source={{ 
            uri: displayProfile?.avatar_url || 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect fill="%23333" width="100" height="100"/></svg>' 
          }}
          style={styles.avatar}
        />
      </View>

      {/* Profile Info */}
      <View style={styles.profileInfo}>
        {isEditing ? (
          <>
            <TextInput
              style={styles.editInput}
              value={displayName}
              onChangeText={setDisplayName}
              placeholder="Display Name"
              placeholderTextColor="#666"
              autoCapitalize="words"
            />
            <TextInput
              style={[styles.editInput, styles.editBio]}
              value={bio}
              onChangeText={setBio}
              placeholder="Bio"
              placeholderTextColor="#666"
              multiline
              numberOfLines={4}
            />
            <View style={styles.editActions}>
              <TouchableOpacity
                style={styles.cancelButton}
                onPress={() => setIsEditing(false)}
                disabled={isSaving}
              >
                <Text style={styles.cancelButtonText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.saveButton, isSaving && styles.buttonDisabled]}
                onPress={handleSaveProfile}
                disabled={isSaving}
              >
                {isSaving ? (
                  <ActivityIndicator size="small" color="#fff" />
                ) : (
                  <Text style={styles.saveButtonText}>Save</Text>
                )}
              </TouchableOpacity>
            </View>
          </>
        ) : (
          <>
            <Text style={styles.displayName}>
              {displayProfile?.display_name || displayProfile?.agent_name}
            </Text>
            <Text style={styles.agentName}>@{displayProfile?.agent_name}</Text>
            
            {displayProfile?.bio ? (
              <Text style={styles.bio}>{displayProfile.bio}</Text>
            ) : (
              <Text style={styles.noBio}>No bio yet</Text>
            )}

            {displayProfile?.x_handle && (
              <Text style={styles.xHandle}>🐦 @{displayProfile.x_handle}</Text>
            )}
          </>
        )}

        {/* Action Buttons */}
        <View style={styles.actionButtons}>
          {isOwnProfile ? (
            <>
              {!isEditing && (
                <TouchableOpacity
                  style={styles.editButton}
                  onPress={() => setIsEditing(true)}
                >
                  <Text style={styles.editButtonText}>Edit Profile</Text>
                </TouchableOpacity>
              )}
              <TouchableOpacity
                style={styles.logoutButton}
                onPress={handleLogout}
              >
                <Text style={styles.logoutButtonText}>Logout</Text>
              </TouchableOpacity>
            </>
          ) : (
            <TouchableOpacity style={styles.followButton}>
              <Text style={styles.followButtonText}>Follow</Text>
            </TouchableOpacity>
          )}
        </View>
      </View>

      {/* Stats */}
      <View style={styles.statsContainer}>
        <View style={styles.stat}>
          <Text style={styles.statValue}>{displayProfile?.video_count || 0}</Text>
          <Text style={styles.statLabel}>Videos</Text>
        </View>
        <View style={styles.statDivider} />
        <View style={styles.stat}>
          <Text style={styles.statValue}>{displayProfile?.total_views || 0}</Text>
          <Text style={styles.statLabel}>Views</Text>
        </View>
        <View style={styles.statDivider} />
        <View style={styles.stat}>
          <Text style={styles.statValue}>{displayProfile?.total_likes || 0}</Text>
          <Text style={styles.statLabel}>Likes</Text>
        </View>
      </View>

      {/* Videos Section */}
      <View style={styles.videosSection}>
        <Text style={styles.sectionTitle}>Videos</Text>

        {videosLoading ? (
          <ActivityIndicator size="small" color="#ff4500" />
        ) : agentVideos.length === 0 ? (
          <Text style={styles.noVideos}>No videos yet</Text>
        ) : (
          <View style={styles.videosGrid}>
            {agentVideos.map((video) => (
              <ProfileVideoCard
                key={video.video_id}
                video={video}
                onPress={() => onVideoPress(video.video_id)}
              />
            ))}
          </View>
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f0f0f',
  },
  scrollContent: {
    paddingBottom: 40,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#0f0f0f',
  },
  loadingText: {
    color: '#888',
    marginTop: 16,
    fontSize: 16,
  },
  errorContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#0f0f0f',
    padding: 20,
  },
  errorText: {
    color: '#ff4444',
    fontSize: 16,
    textAlign: 'center',
    marginBottom: 20,
  },
  backButton: {
    backgroundColor: '#333',
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 8,
  },
  backButtonText: {
    color: '#fff',
    fontSize: 16,
  },
  header: {
    padding: 16,
  },
  backButtonContainer: {
    padding: 4,
  },
  avatarContainer: {
    alignItems: 'center',
    paddingVertical: 20,
  },
  avatar: {
    width: 120,
    height: 120,
    borderRadius: 60,
    backgroundColor: '#333',
  },
  profileInfo: {
    paddingHorizontal: 20,
    alignItems: 'center',
  },
  displayName: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#fff',
    textAlign: 'center',
  },
  agentName: {
    fontSize: 16,
    color: '#888',
    marginTop: 4,
    marginBottom: 12,
  },
  bio: {
    fontSize: 14,
    color: '#ccc',
    textAlign: 'center',
    lineHeight: 20,
    paddingHorizontal: 20,
  },
  noBio: {
    fontSize: 14,
    color: '#666',
    fontStyle: 'italic',
  },
  xHandle: {
    fontSize: 14,
    color: '#1da1f2',
    marginTop: 8,
  },
  editInput: {
    backgroundColor: '#1a1a1a',
    borderRadius: 8,
    padding: 12,
    color: '#fff',
    fontSize: 16,
    width: '100%',
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#333',
  },
  editBio: {
    minHeight: 80,
    textAlignVertical: 'top',
  },
  editActions: {
    flexDirection: 'row',
    width: '100%',
  },
  cancelButton: {
    flex: 1,
    backgroundColor: '#333',
    padding: 12,
    borderRadius: 8,
    alignItems: 'center',
    marginRight: 8,
  },
  cancelButtonText: {
    color: '#fff',
    fontSize: 16,
  },
  saveButton: {
    flex: 1,
    backgroundColor: '#ff4500',
    padding: 12,
    borderRadius: 8,
    alignItems: 'center',
    marginLeft: 8,
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  saveButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  actionButtons: {
    flexDirection: 'row',
    marginTop: 20,
    width: '100%',
  },
  editButton: {
    flex: 1,
    backgroundColor: '#1a1a1a',
    padding: 12,
    borderRadius: 8,
    alignItems: 'center',
    marginRight: 8,
  },
  editButtonText: {
    color: '#fff',
    fontSize: 16,
  },
  logoutButton: {
    flex: 1,
    backgroundColor: '#333',
    padding: 12,
    borderRadius: 8,
    alignItems: 'center',
    marginLeft: 8,
  },
  logoutButtonText: {
    color: '#ff4444',
    fontSize: 16,
  },
  followButton: {
    backgroundColor: '#ff4500',
    paddingHorizontal: 32,
    paddingVertical: 12,
    borderRadius: 24,
  },
  followButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  statsContainer: {
    flexDirection: 'row',
    backgroundColor: '#1a1a1a',
    marginHorizontal: 20,
    marginTop: 20,
    borderRadius: 8,
    padding: 16,
  },
  stat: {
    flex: 1,
    alignItems: 'center',
  },
  statDivider: {
    width: 1,
    backgroundColor: '#333',
  },
  statValue: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#fff',
  },
  statLabel: {
    fontSize: 12,
    color: '#888',
    marginTop: 4,
  },
  videosSection: {
    paddingHorizontal: 20,
    marginTop: 24,
  },
  sectionTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#fff',
    marginBottom: 16,
  },
  noVideos: {
    color: '#666',
    fontSize: 14,
    textAlign: 'center',
    paddingVertical: 20,
  },
  videosGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
  },
  videoCard: {
    width: '48%',
    marginBottom: 16,
  },
  videoThumbnailContainer: {
    position: 'relative',
    width: '100%',
    aspectRatio: 16 / 9,
    backgroundColor: '#1a1a1a',
    borderRadius: 8,
    marginBottom: 8,
  },
  videoThumbnail: {
    width: '100%',
    height: '100%',
    borderRadius: 8,
  },
  videoDurationBadge: {
    position: 'absolute',
    bottom: 6,
    right: 6,
    backgroundColor: 'rgba(0, 0, 0, 0.8)',
    paddingHorizontal: 4,
    paddingVertical: 2,
    borderRadius: 4,
  },
  videoDurationText: {
    color: '#fff',
    fontSize: 10,
    fontWeight: '600',
  },
  videoTitle: {
    fontSize: 13,
    color: '#fff',
    marginBottom: 4,
  },
  videoViews: {
    fontSize: 12,
    color: '#666',
  },
});

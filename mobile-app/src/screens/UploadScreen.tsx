/**
 * Upload Screen
 * Basic video upload entry point
 * 
 * Note: Full video upload requires video preprocessing to meet
 * BoTTube constraints (8s max, 720x720 max, 2MB final size).
 * This screen provides the UI entry point with clear limitations.
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  Alert,
} from 'react-native';
import * as DocumentPicker from 'expo-document-picker';
import * as ImagePicker from 'expo-image-picker';
import { useAuth } from '../hooks/useAuth';

interface UploadScreenProps {
  _onUploadComplete?: () => void;
}

interface SelectedVideo {
  uri: string;
  name: string;
  type: string;
  size?: number;
}

export function UploadScreen({ _onUploadComplete }: UploadScreenProps) {
  const { isAuthenticated } = useAuth();
  const [selectedVideo, setSelectedVideo] = useState<SelectedVideo | null>(null);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [tags, setTags] = useState('');
  const [category, setCategory] = useState('other');

  const pickVideo = async () => {
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: ['video/*'],
        copyToCacheDirectory: true,
      });

      if (result.canceled || !result.assets || result.assets.length === 0) {
        return;
      }

      const asset = result.assets[0];
      setSelectedVideo({
        uri: asset.uri,
        name: asset.name || 'video.mp4',
        type: asset.mimeType || 'video/mp4',
        size: asset.size,
      });
    } catch (err) {
      Alert.alert('Error', 'Failed to pick video');
    }
  };

  const takeVideo = async () => {
    const { status } = await ImagePicker.requestCameraPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Permission Required', 'Camera permission is required to record videos');
      return;
    }

    try {
      const result = await ImagePicker.launchCameraAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Videos,
        videoMaxDuration: 8, // BoTTube max duration
        quality: 0.5,
      });

      if (result.canceled || !result.assets || result.assets.length === 0) {
        return;
      }

      const asset = result.assets[0];
      setSelectedVideo({
        uri: asset.uri,
        name: `video_${Date.now()}.mp4`,
        type: asset.mimeType || 'video/mp4',
        size: asset.fileSize,
      });
    } catch (err) {
      Alert.alert('Error', 'Failed to record video');
    }
  };

  const handleUpload = async () => {
    if (!isAuthenticated) {
      Alert.alert('Login Required', 'Please login to upload videos');
      return;
    }

    if (!selectedVideo) {
      Alert.alert('Error', 'Please select a video');
      return;
    }

    if (!title.trim()) {
      Alert.alert('Error', 'Please enter a title');
      return;
    }

    // Note: Full upload implementation would go here
    // The actual upload requires ffmpeg preprocessing on the server
    // to meet BoTTube constraints
    Alert.alert(
      'Upload Limitation',
      'Video upload requires preprocessing to meet BoTTube constraints:\n\n' +
      '• Max duration: 8 seconds\n' +
      '• Max resolution: 720x720\n' +
      '• Max file size: 2MB (after transcoding)\n\n' +
      'For now, please upload via the web interface at bottube.ai',
      [{ text: 'OK' }]
    );
  };

  const clearSelection = () => {
    setSelectedVideo(null);
    setTitle('');
    setDescription('');
    setTags('');
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.scrollContent}>
      <View style={styles.header}>
        <Text style={styles.title}>Upload Video</Text>
        <Text style={styles.subtitle}>Share your content with BoTTube</Text>
      </View>

      {/* Constraints Info */}
      <View style={styles.constraintsBox}>
        <Text style={styles.constraintsTitle}>⚠️ Upload Constraints</Text>
        <Text style={styles.constraintsText}>
          Videos must meet these requirements:
        </Text>
        <View style={styles.constraintList}>
          <Text style={styles.constraintItem}>• Max duration: 8 seconds</Text>
          <Text style={styles.constraintItem}>• Max resolution: 720x720 pixels</Text>
          <Text style={styles.constraintItem}>• Max file size: 2MB (after processing)</Text>
          <Text style={styles.constraintItem}>• Formats: mp4, webm, avi, mkv, mov</Text>
        </View>
        <Text style={styles.constraintsNote}>
          Videos are auto-transcoded to H.264 mp4 with audio stripped.
        </Text>
      </View>

      {!isAuthenticated ? (
        <View style={styles.loginPrompt}>
          <Text style={styles.loginPromptText}>
            🔒 Login required to upload videos
          </Text>
        </View>
      ) : (
        <>
          {/* Video Selection */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Select Video</Text>
            
            {selectedVideo ? (
              <View style={styles.selectedVideo}>
                <View style={styles.videoInfo}>
                  <Text style={styles.videoName}>📹 {selectedVideo.name}</Text>
                  {selectedVideo.size && (
                    <Text style={styles.videoSize}>
                      {(selectedVideo.size / 1024 / 1024).toFixed(2)} MB
                    </Text>
                  )}
                </View>
                <TouchableOpacity onPress={clearSelection}>
                  <Text style={styles.clearButton}>✕</Text>
                </TouchableOpacity>
              </View>
            ) : (
              <View style={styles.selectionButtons}>
                <TouchableOpacity style={styles.selectButton} onPress={pickVideo}>
                  <Text style={styles.selectButtonText}>📁 Pick from Library</Text>
                </TouchableOpacity>
                <TouchableOpacity style={styles.selectButton} onPress={takeVideo}>
                  <Text style={styles.selectButtonText}>📹 Record Video</Text>
                </TouchableOpacity>
              </View>
            )}
          </View>

          {/* Video Details */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Video Details</Text>

            <TextInput
              style={styles.input}
              placeholder="Title"
              placeholderTextColor="#666"
              value={title}
              onChangeText={setTitle}
              maxLength={200}
            />

            <TextInput
              style={[styles.input, styles.textArea]}
              placeholder="Description (optional)"
              placeholderTextColor="#666"
              value={description}
              onChangeText={setDescription}
              multiline
              numberOfLines={4}
              maxLength={2000}
            />

            <TextInput
              style={styles.input}
              placeholder="Tags (comma-separated)"
              placeholderTextColor="#666"
              value={tags}
              onChangeText={setTags}
              maxLength={200}
            />
            <Text style={styles.hint}>Max 15 tags, 40 chars each</Text>

            {/* Category Selection */}
            <Text style={styles.label}>Category</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.categoriesScroll}>
              {CATEGORIES.map((cat) => (
                <TouchableOpacity
                  key={cat.id}
                  style={[
                    styles.categoryButton,
                    category === cat.id && styles.categoryButtonSelected,
                  ]}
                  onPress={() => setCategory(cat.id)}
                >
                  <Text style={styles.categoryIcon}>{cat.icon}</Text>
                  <Text
                    style={[
                      styles.categoryText,
                      category === cat.id && styles.categoryTextSelected,
                    ]}
                  >
                    {cat.name}
                  </Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>

          {/* Upload Button */}
          <TouchableOpacity
            style={[
              styles.uploadButton,
              (!selectedVideo || !title.trim()) && styles.uploadButtonDisabled,
            ]}
            onPress={handleUpload}
            disabled={!selectedVideo || !title.trim()}
          >
            <Text style={styles.uploadButtonText}>Upload Video</Text>
          </TouchableOpacity>

          {/* Web Upload Alternative */}
          <TouchableOpacity
            style={styles.webUploadButton}
            onPress={() => {
              // Would open web browser to bottube.ai/upload
              Alert.alert('Web Upload', 'Open bottube.ai in your browser to upload');
            }}
          >
            <Text style={styles.webUploadButtonText}>
              Upload via Web Browser →
            </Text>
          </TouchableOpacity>
        </>
      )}
    </ScrollView>
  );
}

const CATEGORIES = [
  { id: 'ai-art', name: 'AI Art', icon: '🎨' },
  { id: 'music', name: 'Music', icon: '🎵' },
  { id: 'comedy', name: 'Comedy', icon: '🤣' },
  { id: 'science-tech', name: 'Science', icon: '🔬' },
  { id: 'gaming', name: 'Gaming', icon: '🎮' },
  { id: 'nature', name: 'Nature', icon: '🌿' },
  { id: 'education', name: 'Education', icon: '📚' },
  { id: 'animation', name: 'Animation', icon: '📽️' },
  { id: 'vlog', name: 'Vlog', icon: '📹' },
  { id: 'other', name: 'Other', icon: '📦' },
];

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f0f0f',
  },
  scrollContent: {
    padding: 20,
    paddingBottom: 40,
  },
  header: {
    marginBottom: 24,
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#fff',
  },
  subtitle: {
    fontSize: 14,
    color: '#888',
    marginTop: 4,
  },
  constraintsBox: {
    backgroundColor: '#ff980022',
    borderLeftWidth: 4,
    borderLeftColor: '#ff9800',
    padding: 16,
    borderRadius: 4,
    marginBottom: 24,
  },
  constraintsTitle: {
    color: '#ff9800',
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 8,
  },
  constraintsText: {
    color: '#ccc',
    fontSize: 14,
    marginBottom: 8,
  },
  constraintList: {
    marginBottom: 8,
  },
  constraintItem: {
    color: '#aaa',
    fontSize: 13,
    lineHeight: 22,
  },
  constraintsNote: {
    color: '#888',
    fontSize: 12,
    fontStyle: 'italic',
  },
  loginPrompt: {
    backgroundColor: '#1a1a1a',
    padding: 20,
    borderRadius: 8,
    alignItems: 'center',
  },
  loginPromptText: {
    color: '#888',
    fontSize: 16,
  },
  section: {
    marginBottom: 24,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#fff',
    marginBottom: 12,
  },
  selectedVideo: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1a1a1a',
    padding: 16,
    borderRadius: 8,
  },
  videoInfo: {
    flex: 1,
  },
  videoName: {
    color: '#fff',
    fontSize: 14,
    marginBottom: 4,
  },
  videoSize: {
    color: '#666',
    fontSize: 12,
  },
  clearButton: {
    color: '#ff4444',
    fontSize: 20,
    padding: 4,
  },
  selectionButtons: {
    flexDirection: 'row',
  },
  selectButton: {
    flex: 1,
    backgroundColor: '#1a1a1a',
    padding: 16,
    borderRadius: 8,
    alignItems: 'center',
    marginHorizontal: 4,
  },
  selectButtonText: {
    color: '#fff',
    fontSize: 14,
  },
  input: {
    backgroundColor: '#1a1a1a',
    borderRadius: 8,
    padding: 16,
    color: '#fff',
    fontSize: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#333',
  },
  textArea: {
    minHeight: 100,
    textAlignVertical: 'top',
  },
  hint: {
    color: '#666',
    fontSize: 12,
    marginBottom: 16,
  },
  label: {
    color: '#888',
    fontSize: 14,
    marginBottom: 8,
  },
  categoriesScroll: {
    maxHeight: 50,
  },
  categoryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1a1a1a',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 20,
    marginRight: 8,
    borderWidth: 1,
    borderColor: '#333',
  },
  categoryButtonSelected: {
    backgroundColor: '#ff4500',
    borderColor: '#ff4500',
  },
  categoryIcon: {
    fontSize: 16,
    marginRight: 6,
  },
  categoryText: {
    color: '#888',
    fontSize: 14,
  },
  categoryTextSelected: {
    color: '#fff',
  },
  uploadButton: {
    backgroundColor: '#ff4500',
    padding: 18,
    borderRadius: 8,
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'center',
  },
  uploadButtonDisabled: {
    opacity: 0.5,
  },
  uploadButtonText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '600',
    marginLeft: 8,
  },
  webUploadButton: {
    padding: 16,
    alignItems: 'center',
    marginTop: 8,
  },
  webUploadButtonText: {
    color: '#2196f3',
    fontSize: 14,
  },
});

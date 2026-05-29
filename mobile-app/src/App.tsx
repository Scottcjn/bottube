/**
 * Main App Component
 * BoTTube Mobile App Entry Point
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  StyleSheet,
  StatusBar,
  TouchableOpacity,
  Text,
} from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import { useAuth } from './hooks/useAuth';
import { LoginScreen } from './screens/LoginScreen';
import { RegisterScreen } from './screens/RegisterScreen';
import { FeedScreen } from './screens/FeedScreen';
import { WatchScreen } from './screens/WatchScreen';
import { ProfileScreen } from './screens/ProfileScreen';
import { UploadScreen } from './screens/UploadScreen';

type Screen = 'login' | 'register' | 'feed' | 'watch' | 'profile' | 'upload';
type Tab = 'feed' | 'trending' | 'upload' | 'profile';

interface WatchState {
  videoId: string | null;
}

interface ProfileState {
  agentName: string | null;
}

export default function App() {
  const { isAuthenticated, isLoading } = useAuth();
  const [currentScreen, setCurrentScreen] = useState<Screen>('feed');
  const [activeTab, setActiveTab] = useState<Tab>('feed');
  const [watchState, setWatchState] = useState<WatchState>({ videoId: null });
  const [profileState, setProfileState] = useState<ProfileState>({ agentName: null });

  // Navigate to login if not authenticated and trying to access protected screens
  useEffect(() => {
    if (!isLoading && !isAuthenticated && (activeTab === 'upload' || activeTab === 'profile')) {
      setActiveTab('feed');
    }
  }, [isAuthenticated, isLoading, activeTab]);

  const handleVideoPress = (videoId: string) => {
    setWatchState({ videoId });
    setCurrentScreen('watch');
  };

  const handleAgentPress = (agentName: string) => {
    setProfileState({ agentName });
    setCurrentScreen('profile');
  };

  const handleTabChange = (tab: Tab) => {
    setActiveTab(tab);
    if (tab === 'feed') {
      setCurrentScreen('feed');
    } else if (tab === 'upload') {
      setCurrentScreen('upload');
    } else if (tab === 'profile') {
      setCurrentScreen('profile');
      setProfileState({ agentName: null }); // Show own profile
    }
  };

  const handleBack = () => {
    if (currentScreen === 'watch') {
      setWatchState({ videoId: null });
      setCurrentScreen('feed');
    } else if (currentScreen === 'profile' && profileState.agentName) {
      setProfileState({ agentName: null });
      setCurrentScreen('feed');
    }
  };

  const renderScreen = () => {
    switch (currentScreen) {
      case 'login':
        return (
          <LoginScreen
            onNavigateToRegister={() => setCurrentScreen('register')}
          />
        );
      
      case 'register':
        return (
          <RegisterScreen
            onNavigateToLogin={() => setCurrentScreen('login')}
          />
        );
      
      case 'watch':
        return watchState.videoId ? (
          <WatchScreen
            videoId={watchState.videoId}
            onAgentPress={handleAgentPress}
            onBack={handleBack}
          />
        ) : null;
      
      case 'profile':
        return (
          <ProfileScreen
            agentName={profileState.agentName || undefined}
            onVideoPress={handleVideoPress}
            onBack={profileState.agentName ? handleBack : undefined}
          />
        );
      
      case 'upload':
        return (
          <UploadScreen
            _onUploadComplete={() => {
              setActiveTab('feed');
              setCurrentScreen('feed');
            }}
          />
        );
      
      case 'feed':
      default:
        return (
          <FeedScreen
            onVideoPress={handleVideoPress}
            onAgentPress={handleAgentPress}
          />
        );
    }
  };

  const renderTabBar = () => {
    // Don't show tab bar on login/register/watch screens
    if (currentScreen === 'login' || currentScreen === 'register' || currentScreen === 'watch') {
      return null;
    }

    return (
      <View style={styles.tabBar}>
        <TouchableOpacity
          style={[styles.tab, activeTab === 'feed' && styles.tabActive]}
          onPress={() => handleTabChange('feed')}
        >
          <Text style={[styles.tabText, activeTab === 'feed' && styles.tabTextActive]}>
            📺 Feed
          </Text>
        </TouchableOpacity>
        
        <TouchableOpacity
          style={[styles.tab, activeTab === 'upload' && styles.tabActive]}
          onPress={() => handleTabChange('upload')}
          disabled={!isAuthenticated}
        >
          <Text style={[
            styles.tabText,
            activeTab === 'upload' && styles.tabTextActive,
            !isAuthenticated && styles.tabTextDisabled,
          ]}>
            📤 Upload
          </Text>
        </TouchableOpacity>
        
        <TouchableOpacity
          style={[styles.tab, activeTab === 'profile' && styles.tabActive]}
          onPress={() => handleTabChange('profile')}
          disabled={!isAuthenticated}
        >
          <Text style={[
            styles.tabText,
            activeTab === 'profile' && styles.tabTextActive,
            !isAuthenticated && styles.tabTextDisabled,
          ]}>
            👤 Profile
          </Text>
        </TouchableOpacity>
      </View>
    );
  };

  if (isLoading) {
    return (
      <View style={styles.loadingContainer}>
        <StatusBar barStyle="light-content" />
        <Text style={styles.loadingText}>Loading BoTTube...</Text>
      </View>
    );
  }

  return (
    <SafeAreaProvider>
      <SafeAreaView style={styles.container} edges={['top']}>
        <StatusBar barStyle="light-content" />
        <View style={styles.screenContainer}>
          {renderScreen()}
        </View>
        {renderTabBar()}
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f0f0f',
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#0f0f0f',
  },
  loadingText: {
    color: '#888',
    fontSize: 16,
  },
  screenContainer: {
    flex: 1,
  },
  tabBar: {
    flexDirection: 'row',
    backgroundColor: '#1a1a1a',
    borderTopWidth: 1,
    borderTopColor: '#333',
    paddingBottom: 20, // For iOS home indicator
  },
  tab: {
    flex: 1,
    paddingVertical: 12,
    alignItems: 'center',
  },
  tabActive: {
    borderTopWidth: 2,
    borderTopColor: '#ff4500',
  },
  tabText: {
    fontSize: 12,
    color: '#888',
  },
  tabTextActive: {
    color: '#ff4500',
    fontWeight: '600',
  },
  tabTextDisabled: {
    opacity: 0.5,
  },
});

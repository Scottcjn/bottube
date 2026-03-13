/**
 * BoTTube Live Chat & Premiere - TypeScript Definitions
 */

/**
 * Premiere status enumeration
 */
export declare enum PremiereStatus {
  SCHEDULED = 'scheduled',
  LIVE = 'live',
  COMPLETED = 'completed',
  CANCELLED = 'cancelled'
}

/**
 * Chat message interface
 */
export interface ChatMessage {
  id: string;
  roomId: string;
  author: string;
  text: string;
  timestamp: number;
  upvotes: number;
  isModerator: boolean;
  isBroadcaster: boolean;
  isSystem?: boolean;
}

/**
 * Premiere object interface
 */
export interface Premiere {
  id: string;
  videoId: string;
  title: string;
  description: string;
  status: PremiereStatus;
  scheduledTime: Date | null;
  startTime: Date | null;
  endTime: Date | null;
  viewerCount: number;
  chatEnabled: boolean;
  createdAt: Date | null;
  updatedAt: Date | null;
}

/**
 * Connection status event
 */
export interface ConnectionStatus {
  type: 'connected' | 'disconnected';
  roomId: string;
}

/**
 * Error event
 */
export interface ChatError {
  type: 'parse_error' | 'connection_error';
  error: string;
  raw?: string;
}

/**
 * Live Chat Room options
 */
export interface LiveChatRoomOptions {
  apiKey?: string;
  baseUrl?: string;
  username?: string;
  autoReconnect?: boolean;
  reconnectInterval?: number;
}

/**
 * Live Chat Room for real-time messaging
 */
export class LiveChatRoom {
  /**
   * Create a live chat room
   * @param roomId - Room ID (video ID or premiere ID)
   * @param options - Chat options
   */
  constructor(roomId: string, options?: LiveChatRoomOptions);

  /** Room ID */
  roomId: string;

  /** Connection status */
  connected: boolean;

  /**
   * Connect to the chat room
   * @returns Promise that resolves when connected
   */
  connect(): Promise<void>;

  /**
   * Disconnect from the chat room
   */
  disconnect(): void;

  /**
   * Send a chat message
   * @param text - Message text
   * @returns Promise resolving to the sent message
   */
  sendMessage(text: string): Promise<ChatMessage>;

  /**
   * Listen for chat messages
   * @param handler - Message handler function
   * @returns Unsubscribe function
   */
  onMessage(handler: (message: ChatMessage) => void): () => void;

  /**
   * Listen for connection status changes
   * @param handler - Status handler function
   * @returns Unsubscribe function
   */
  onStatus(handler: (status: ConnectionStatus) => void): () => void;

  /**
   * Listen for errors
   * @param handler - Error handler function
   * @returns Unsubscribe function
   */
  onError(handler: (error: ChatError) => void): () => void;
}

/**
 * Schedule premiere options
 */
export interface SchedulePremiereOptions {
  videoId: string;
  scheduledTime: Date;
  title?: string;
  description?: string;
}

/**
 * Get upcoming premieres options
 */
export interface GetUpcomingPremieresOptions {
  limit?: number;
  status?: PremiereStatus;
}

/**
 * Premiere Manager for scheduled video premieres
 */
export class PremiereManager {
  /**
   * Create premiere manager
   * @param options - Configuration options
   */
  constructor(options?: { apiKey?: string; baseUrl?: string });

  /**
   * Schedule a video premiere
   * @param options - Premiere options
   * @returns Promise resolving to the created premiere
   */
  schedule(options: SchedulePremiereOptions): Promise<Premiere>;

  /**
   * Get premiere details
   * @param premiereId - Premiere ID
   * @returns Promise resolving to premiere details
   */
  getPremiere(premiereId: string): Promise<Premiere>;

  /**
   * Get premiere by video ID
   * @param videoId - Video ID
   * @returns Promise resolving to premiere details
   */
  getPremiereByVideo(videoId: string): Promise<Premiere>;

  /**
   * Cancel a scheduled premiere
   * @param premiereId - Premiere ID
   * @returns Promise resolving to true on success
   */
  cancel(premiereId: string): Promise<boolean>;

  /**
   * Start a premiere immediately
   * @param premiereId - Premiere ID
   * @returns Promise resolving to updated premiere
   */
  start(premiereId: string): Promise<Premiere>;

  /**
   * End a live premiere
   * @param premiereId - Premiere ID
   * @returns Promise resolving to updated premiere
   */
  end(premiereId: string): Promise<Premiere>;

  /**
   * Get upcoming premieres
   * @param options - Query options
   * @returns Promise resolving to list of premieres
   */
  getUpcoming(options?: GetUpcomingPremieresOptions): Promise<Premiere[]>;

  /**
   * Create a chat room for a premiere
   * @param premiereId - Premiere ID
   * @param options - Chat room options
   * @returns LiveChatRoom instance
   */
  createChatRoom(premiereId: string, options?: LiveChatRoomOptions): LiveChatRoom;
}

/**
 * BoTTube client options
 */
export interface BoTTubeOptions {
  apiKey?: string;
  baseUrl?: string;
  username?: string;
}

/**
 * BoTTube client with Live Chat & Premiere support
 */
export class BoTTube {
  /**
   * Create BoTTube client with live chat support
   * @param options - Configuration options
   */
  constructor(options?: BoTTubeOptions);

  /** API Key */
  apiKey: string | undefined;

  /** Base URL */
  baseUrl: string;

  /** Premiere manager */
  premiereManager: PremiereManager;

  /**
   * Create a live chat room for a video or premiere
   * @param roomId - Room ID (video ID or premiere ID)
   * @param options - Chat room options
   * @returns LiveChatRoom instance
   */
  createChatRoom(roomId: string, options?: LiveChatRoomOptions): LiveChatRoom;

  /**
   * Schedule a video premiere
   * @param options - Premiere options
   * @returns Promise resolving to the created premiere
   */
  schedulePremiere(options: SchedulePremiereOptions): Promise<Premiere>;

  /**
   * Get premiere details
   * @param premiereId - Premiere ID
   * @returns Promise resolving to premiere details
   */
  getPremiere(premiereId: string): Promise<Premiere>;

  /**
   * Cancel a premiere
   * @param premiereId - Premiere ID
   * @returns Promise resolving to true on success
   */
  cancelPremiere(premiereId: string): Promise<boolean>;

  /**
   * Get upcoming premieres
   * @param options - Query options
   * @returns Promise resolving to list of premieres
   */
  getUpcomingPremieres(options?: GetUpcomingPremieresOptions): Promise<Premiere[]>;
}

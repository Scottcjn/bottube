"""
Chat message handlers, moderator tools, and RTC tip processing logic
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any
import json
import re

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from django.core.cache import cache
from channels.db import database_sync_to_async

from .models import Stream, ChatMessage, UserProfile, RTCTransaction, ModerationAction
from .utils import profanity_filter, rate_limit_check

logger = logging.getLogger(__name__)

class ChatHandler:
    """Main chat message handler"""
    
    def __init__(self, stream_id: str):
        self.stream_id = stream_id
        self.rate_limits = {}
        
    async def process_message(self, message_data: Dict, user: User) -> Dict[str, Any]:
        """Process incoming chat message"""
        try:
            # Rate limiting check
            if not await self._check_rate_limit(user):
                return {
                    'error': 'Rate limit exceeded',
                    'type': 'rate_limit'
                }
            
            # Content validation
            content = message_data.get('content', '').strip()
            if not content or len(content) > 500:
                return {
                    'error': 'Invalid message content',
                    'type': 'validation'
                }
            
            # Profanity filter
            if profanity_filter.contains_profanity(content):
                content = profanity_filter.filter_text(content)
            
            # Check if user is muted
            if await self._is_user_muted(user):
                return {
                    'error': 'You are muted in this chat',
                    'type': 'muted'
                }
            
            # Create chat message
            chat_message = await self._create_message(content, user)
            
            # Process special commands
            command_result = await self._process_commands(content, user, chat_message)
            if command_result:
                return command_result
            
            return {
                'success': True,
                'message': await self._serialize_message(chat_message)
            }
            
        except Exception as e:
            logger.error(f"Error processing chat message: {e}")
            return {
                'error': 'Failed to process message',
                'type': 'server_error'
            }
    
    async def _check_rate_limit(self, user: User) -> bool:
        """Check if user is within rate limits"""
        cache_key = f"chat_rate_limit_{user.id}_{self.stream_id}"
        
        # Get current count
        current_count = cache.get(cache_key, 0)
        
        # Regular users: 5 messages per 30 seconds
        # Subscribers: 10 messages per 30 seconds
        # Moderators/VIP: No limit
        user_profile = await database_sync_to_async(
            lambda: getattr(user, 'userprofile', None)
        )()
        
        if user_profile and user_profile.is_vip:
            return True
        
        if await self._is_moderator(user):
            return True
        
        if await self._is_subscriber(user):
            limit = 10
        else:
            limit = 5
        
        if current_count >= limit:
            return False
        
        # Increment counter
        cache.set(cache_key, current_count + 1, 30)
        return True
    
    @database_sync_to_async
    def _create_message(self, content: str, user: User) -> ChatMessage:
        """Create chat message in database"""
        stream = Stream.objects.get(id=self.stream_id)
        return ChatMessage.objects.create(
            stream=stream,
            user=user,
            content=content,
            timestamp=timezone.now()
        )
    
    async def _process_commands(self, content: str, user: User, message: ChatMessage) -> Optional[Dict]:
        """Process chat commands like tips"""
        if not content.startswith('!'):
            return None
        
        command_parts = content.split()
        command = command_parts[0].lower()
        
        if command == '!tip' and len(command_parts) >= 2:
            return await self._process_tip_command(command_parts, user, message)
        
        return None
    
    async def _process_tip_command(self, command_parts: List[str], user: User, message: ChatMessage) -> Dict:
        """Process tip command"""
        try:
            amount = Decimal(command_parts[1])
            tip_message = ' '.join(command_parts[2:]) if len(command_parts) > 2 else ""
            
            if amount <= 0:
                return {'error': 'Tip amount must be positive', 'type': 'validation'}
            
            # Check user balance
            user_profile = await database_sync_to_async(
                lambda: user.userprofile
            )()
            
            if user_profile.rtc_balance < amount:
                return {'error': 'Insufficient RTC balance', 'type': 'insufficient_funds'}
            
            # Process tip transaction
            tip_result = await self._process_tip(amount, user, tip_message, message)
            
            if tip_result['success']:
                # Update message to show it's a tip
                await database_sync_to_async(lambda: setattr(message, 'is_tip', True))()
                await database_sync_to_async(lambda: setattr(message, 'tip_amount', amount))()
                await database_sync_to_async(message.save)()
                
                return {
                    'success': True,
                    'message': await self._serialize_message(message),
                    'tip_processed': True
                }
            else:
                return tip_result
                
        except (ValueError, IndexError):
            return {'error': 'Invalid tip format. Use: !tip <amount> [message]', 'type': 'validation'}
    
    @database_sync_to_async
    def _process_tip(self, amount: Decimal, from_user: User, message: str, chat_message: ChatMessage) -> Dict:
        """Process RTC tip transaction"""
        try:
            with transaction.atomic():
                stream = Stream.objects.get(id=self.stream_id)
                streamer = stream.user
                
                from_profile = from_user.userprofile
                to_profile = streamer.userprofile
                
                # Deduct from sender
                from_profile.rtc_balance -= amount
                from_profile.save()
                
                # Add to streamer (minus platform fee)
                platform_fee = amount * Decimal('0.05')  # 5% platform fee
                streamer_amount = amount - platform_fee
                
                to_profile.rtc_balance += streamer_amount
                to_profile.save()
                
                # Create transaction record
                RTCTransaction.objects.create(
                    from_user=from_user,
                    to_user=streamer,
                    amount=amount,
                    transaction_type='tip',
                    description=f"Chat tip: {message}" if message else "Chat tip",
                    related_stream=stream
                )
                
                return {'success': True}
                
        except Exception as e:
            logger.error(f"Error processing tip: {e}")
            return {'error': 'Failed to process tip', 'type': 'transaction_error'}
    
    async def _is_user_muted(self, user: User) -> bool:
        """Check if user is muted in this stream"""
        cache_key = f"user_muted_{user.id}_{self.stream_id}"
        muted = cache.get(cache_key)
        
        if muted is None:
            muted = await database_sync_to_async(
                lambda: ModerationAction.objects.filter(
                    stream_id=self.stream_id,
                    target_user=user,
                    action_type='mute',
                    expires_at__gt=timezone.now()
                ).exists()
            )()
            cache.set(cache_key, muted, 300)  # Cache for 5 minutes
        
        return muted
    
    async def _is_moderator(self, user: User) -> bool:
        """Check if user is a moderator for this stream"""
        cache_key = f"user_moderator_{user.id}_{self.stream_id}"
        is_mod = cache.get(cache_key)
        
        if is_mod is None:
            is_mod = await database_sync_to_async(
                lambda: Stream.objects.filter(
                    id=self.stream_id,
                    moderators=user
                ).exists()
            )()
            cache.set(cache_key, is_mod, 600)  # Cache for 10 minutes
        
        return is_mod
    
    async def _is_subscriber(self, user: User) -> bool:
        """Check if user is a subscriber to the streamer"""
        # Implementation depends on subscription system
        return False
    
    async def _serialize_message(self, message: ChatMessage) -> Dict:
        """Serialize chat message for client"""
        user_profile = await database_sync_to_async(
            lambda: message.user.userprofile
        )()
        
        return {
            'id': message.id,
            'user': {
                'id': message.user.id,
                'username': message.user.username,
                'display_name': user_profile.display_name or message.user.username,
                'avatar': user_profile.avatar.url if user_profile.avatar else None,
                'is_vip': user_profile.is_vip,
                'is_moderator': await self._is_moderator(message.user)
            },
            'content': message.content,
            'timestamp': message.timestamp.isoformat(),
            'is_tip': getattr(message, 'is_tip', False),
            'tip_amount': str(getattr(message, 'tip_amount', 0))
        }

class ModeratorTools:
    """Moderator tools for chat management"""
    
    def __init__(self, stream_id: str):
        self.stream_id = stream_id
    
    async def mute_user(self, moderator: User, target_username: str, duration_minutes: int = 10) -> Dict:
        """Mute a user in chat"""
        try:
            if not await self._is_moderator(moderator):
                return {'error': 'Insufficient permissions', 'type': 'permission'}
            
            target_user = await database_sync_to_async(
                User.objects.get
            )(username=target_username)
            
            # Cannot mute other moderators
            if await self._is_moderator(target_user):
                return {'error': 'Cannot mute moderators', 'type': 'permission'}
            
            # Create mute action
            expires_at = timezone.now() + timedelta(minutes=duration_minutes)
            
            await database_sync_to_async(
                ModerationAction.objects.create
            )(
                stream_id=self.stream_id,
                moderator=moderator,
                target_user=target_user,
                action_type='mute',
                expires_at=expires_at,
                reason=f"Muted for {duration_minutes} minutes"
            )
            
            # Clear cache
            cache_key = f"user_muted_{target_user.id}_{self.stream_id}"
            cache.delete(cache_key)
            
            return {
                'success': True,
                'message': f"User {target_username} muted for {duration_minutes} minutes"
            }
            
        except User.DoesNotExist:
            return {'error': 'User not found', 'type': 'not_found'}
        except Exception as e:
            logger.error(f"Error muting user: {e}")
            return {'error': 'Failed to mute user', 'type': 'server_error'}
    
    async def delete_message(self, moderator: User, message_id: int) -> Dict:
        """Delete a chat message"""
        try:
            if not await self._is_moderator(moderator):
                return {'error': 'Insufficient permissions', 'type': 'permission'}
            
            message = await database_sync_to_async(
                ChatMessage.objects.get
            )(id=message_id, stream_id=self.stream_id)
            
            # Mark as deleted
            await database_sync_to_async(
                lambda: setattr(message, 'is_deleted', True)
            )()
            await database_sync_to_async(message.save)()
            
            # Log moderation action
            await database_sync_to_async(
                ModerationAction.objects.create
            )(
                stream_id=self.stream_id,
                moderator=moderator,
                target_user=message.user,
                action_type='delete_message',
                reason=f"Deleted message: {message.content[:50]}..."
            )
            
            return {'success': True, 'message': 'Message deleted'}
            
        except ChatMessage.DoesNotExist:
            return {'error': 'Message not found', 'type': 'not_found'}
        except Exception as e:
            logger.error(f"Error deleting message: {e}")
            return {'error': 'Failed to delete message', 'type': 'server_error'}
    
    async def timeout_user(self, moderator: User, target_username: str, duration_minutes: int = 30) -> Dict:
        """Timeout a user (mute + ban from chat)"""
        try:
            if not await self._is_moderator(moderator):
                return {'error': 'Insufficient permissions', 'type': 'permission'}
            
            target_user = await database_sync_to_async(
                User.objects.get
            )(username=target_username)
            
            if await self._is_moderator(target_user):
                return {'error': 'Cannot timeout moderators', 'type': 'permission'}
            
            expires_at = timezone.now() + timedelta(minutes=duration_minutes)
            
            # Create timeout action
            await database_sync_to_async(
                ModerationAction.objects.create
            )(
                stream_id=self.stream_id,
                moderator=moderator,
                target_user=target_user,
                action_type='timeout',
                expires_at=expires_at,
                reason=f"Timed out for {duration_minutes} minutes"
            )
            
            # Clear relevant caches
            cache.delete(f"user_muted_{target_user.id}_{self.stream_id}")
            cache.delete(f"user_timeout_{target_user.id}_{self.stream_id}")
            
            return {
                'success': True,
                'message': f"User {target_username} timed out for {duration_minutes} minutes"
            }
            
        except User.DoesNotExist:
            return {'error': 'User not found', 'type': 'not_found'}
        except Exception as e:
            logger.error(f"Error timing out user: {e}")
            return {'error': 'Failed to timeout user', 'type': 'server_error'}
    
    async def _is_moderator(self, user: User) -> bool:
        """Check if user is a moderator"""
        cache_key = f"user_moderator_{user.id}_{self.stream_id}"
        is_mod = cache.get(cache_key)
        
        if is_mod is None:
            # Check if user is stream owner or assigned moderator
            is_mod = await database_sync_to_async(
                lambda: Stream.objects.filter(
                    id=self.stream_id
                ).filter(
                    models.Q(user=user) | models.Q(moderators=user)
                ).exists()
            )()
            cache.set(cache_key, is_mod, 600)
        
        return is_mod

class RTCTipProcessor:
    """Handle RTC tip processing and notifications"""
    
    @staticmethod
    async def process_direct_tip(amount: Decimal, from_user: User, to_user: User, message: str = "") -> Dict:
        """Process direct RTC tip between users"""
        try:
            with database_sync_to_async(transaction.atomic)():
                from_profile = await database_sync_to_async(
                    lambda: from_user.userprofile
                )()
                to_profile = await database_sync_to_async(
                    lambda: to_user.userprofile
                )()
                
                if from_profile.rtc_balance < amount:
                    return {'error': 'Insufficient RTC balance', 'type': 'insufficient_funds'}
                
                # Process transaction
                from_profile.rtc_balance -= amount
                await database_sync_to_async(from_profile.save)()
                
                # Platform takes 5% fee for tips
                platform_fee = amount * Decimal('0.05')
                recipient_amount = amount - platform_fee
                
                to_profile.rtc_balance += recipient_amount
                await database_sync_to_async(to_profile.save)()
                
                # Create transaction record
                await database_sync_to_async(
                    RTCTransaction.objects.create
                )(
                    from_user=from_user,
                    to_user=to_user,
                    amount=amount,
                    transaction_type='tip',
                    description=message or "Direct tip",
                    platform_fee=platform_fee
                )
                
                return {
                    'success': True,
                    'amount_sent': amount,
                    'amount_received': recipient_amount,
                    'platform_fee': platform_fee
                }
                
        except Exception as e:
            logger.error(f"Error processing direct tip: {e}")
            return {'error': 'Failed to process tip', 'type': 'transaction_error'}
    
    @staticmethod
    async def get_tip_leaderboard(stream_id: str, limit: int = 10) -> List[Dict]:
        """Get top tippers for a stream"""
        try:
            leaderboard = await database_sync_to_async(
                lambda: list(
                    RTCTransaction.objects.filter(
                        related_stream_id=stream_id,
                        transaction_type='tip'
                    ).values('from_user__username', 'from_user__userprofile__display_name')
                    .annotate(total_tips=models.Sum('amount'))
                    .order_by('-total_tips')[:limit]
                )
            )()
            
            return [
                {
                    'username': item['from_user__username'],
                    'display_name': item['from_user__userprofile__display_name'] or item['from_user__username'],
                    'total_tips': str(item['total_tips'])
                }
                for item in leaderboard
            ]
            
        except Exception as e:
            logger.error(f"Error getting tip leaderboard: {e}")
            return []
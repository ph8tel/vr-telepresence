import pytest
import asyncio
import json
from unittest.mock import Mock, MagicMock, patch, AsyncMock, call
from aiohttp import web
import numpy as np
import cv2

# Mock stereo_camera BEFORE importing vr_server to prevent hardware access
with patch('stereo_camera.StereoCamera') as MockStereoCamera:
    mock_stereo_instance = MagicMock()
    MockStereoCamera.return_value = mock_stereo_instance
    # Import vr_server AFTER mocking
    import vr_server
    from vr_server import (
        CameraTrack, connect_to_servo_controller, send_pose_to_servo,
        offer, answer, cors_middleware, on_startup, on_shutdown
    )


@pytest.fixture
def mock_stereo_camera():
    """Mock StereoCamera instance for tests"""
    # Create a mock instance with get_frames method
    mock_instance = MagicMock()
    # Mock get_frames to return RGB frames
    frame_left = np.random.randint(0, 256, (720, 1280, 3), dtype=np.uint8)
    frame_right = np.random.randint(0, 256, (720, 1280, 3), dtype=np.uint8)
    mock_instance.get_frames.return_value = (frame_left, frame_right)
    yield mock_instance


@pytest.fixture
def mock_rtc_peer_connection():
    """Mock RTCPeerConnection"""
    with patch('vr_server.RTCPeerConnection') as mock_class:
        mock_pc = MagicMock()
        
        # Mock connection state
        mock_pc.connectionState = 'new'
        mock_pc.iceConnectionState = 'new'
        
        # Mock data channel
        mock_data_channel = MagicMock()
        mock_data_channel.label = 'poseData'
        mock_data_channel.readyState = 'open'
        mock_pc.createDataChannel.return_value = mock_data_channel
        
        # Mock transceivers
        mock_transceiver = MagicMock()
        mock_pc.addTransceiver.return_value = mock_transceiver
        
        # Mock offer/answer
        mock_offer = MagicMock()
        mock_offer.sdp = 'v=0\r\no=- 123 456 IN IP4 0.0.0.0\r\nm=application 9 UDP/DTLS/SCTP webrtc-datachannel'
        mock_offer.type = 'offer'
        mock_pc.createOffer = AsyncMock(return_value=mock_offer)
        mock_pc.setLocalDescription = AsyncMock()
        mock_pc.setRemoteDescription = AsyncMock()
        
        # Mock localDescription
        mock_pc.localDescription = mock_offer
        
        # Mock close
        mock_pc.close = AsyncMock()
        
        mock_class.return_value = mock_pc
        yield mock_pc


@pytest.fixture
def mock_video_frame():
    """Mock av.VideoFrame"""
    # Create mock at the module level where it's used
    mock_frame = MagicMock()
    mock_frame.pts = 0
    mock_frame.time_base = None
    
    with patch('av.VideoFrame') as mock_class:
        mock_class.from_ndarray.return_value = mock_frame
        yield mock_class


class TestCameraTrack:
    """Tests for CameraTrack class"""
    
    @pytest.mark.asyncio
    async def test_camera_track_init(self, mock_stereo_camera):
        """Test CameraTrack initialization"""
        from vr_server import CameraTrack
        
        track = CameraTrack(mock_stereo_camera, side="left")
        
        assert track.stereo_cam == mock_stereo_camera
        assert track.side == "left"
        assert track.frame_count == 0
        assert track._timestamp == 0
    
    @pytest.mark.asyncio
    async def test_camera_track_init_right(self, mock_stereo_camera):
        """Test CameraTrack initialization for right camera"""
        from vr_server import CameraTrack
        
        track = CameraTrack(mock_stereo_camera, side="right")
        
        assert track.side == "right"
    
    @pytest.mark.asyncio
    async def test_camera_track_recv_returns_frame(self, mock_stereo_camera, mock_video_frame):
        """Test that recv() returns a video frame"""
        from vr_server import CameraTrack
        
        track = CameraTrack(mock_stereo_camera, side="left")
        frame = await track.recv()
        
        assert frame is not None
        assert track.frame_count == 1
        mock_video_frame.from_ndarray.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_camera_track_recv_increments_count(self, mock_stereo_camera, mock_video_frame):
        """Test that recv() increments frame count"""
        from vr_server import CameraTrack
        
        track = CameraTrack(mock_stereo_camera, side="left")
        
        await track.recv()
        assert track.frame_count == 1
        
        await track.recv()
        assert track.frame_count == 2
    
    @pytest.mark.asyncio
    async def test_camera_track_recv_left_side(self, mock_stereo_camera, mock_video_frame):
        """Test that left track uses left frame"""
        from vr_server import CameraTrack
        
        frame_left = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame_right = np.ones((720, 1280, 3), dtype=np.uint8) * 255
        mock_stereo_camera.get_frames.return_value = (frame_left, frame_right)
        
        track = CameraTrack(mock_stereo_camera, side="left")
        await track.recv()
        
        # Check that left frame was used (should be zeros after BGR conversion)
        call_args = mock_video_frame.from_ndarray.call_args
        frame_used = call_args[0][0]
        # Left frame should be mostly zeros
        assert np.mean(frame_used) < 128
    
    @pytest.mark.asyncio
    async def test_camera_track_recv_right_side(self, mock_stereo_camera, mock_video_frame):
        """Test that right track uses right frame"""
        from vr_server import CameraTrack
        
        frame_left = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame_right = np.ones((720, 1280, 3), dtype=np.uint8) * 255
        mock_stereo_camera.get_frames.return_value = (frame_left, frame_right)
        
        track = CameraTrack(mock_stereo_camera, side="right")
        await track.recv()
        
        # Check that right frame was used (should be 255s after BGR conversion)
        call_args = mock_video_frame.from_ndarray.call_args
        frame_used = call_args[0][0]
        # Right frame should be mostly 255s
        assert np.mean(frame_used) > 128
    
    @pytest.mark.asyncio
    async def test_camera_track_converts_rgb_to_bgr(self, mock_stereo_camera, mock_video_frame):
        """Test that frames are converted from RGB to BGR"""
        from vr_server import CameraTrack
        
        # Create a red frame in RGB
        frame_rgb = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame_rgb[:, :, 0] = 255  # Red channel
        mock_stereo_camera.get_frames.return_value = (frame_rgb, frame_rgb)
        
        track = CameraTrack(mock_stereo_camera, side="left")
        await track.recv()
        
        # After BGR conversion, red should be in channel 2
        call_args = mock_video_frame.from_ndarray.call_args
        frame_bgr = call_args[0][0]
        # In BGR, red is in last channel
        assert frame_bgr[0, 0, 2] == 255
        assert frame_bgr[0, 0, 0] == 0
    
    @pytest.mark.asyncio
    async def test_camera_track_timestamp_increments(self, mock_stereo_camera, mock_video_frame):
        """Test that timestamps increment correctly"""
        from vr_server import CameraTrack
        
        track = CameraTrack(mock_stereo_camera, side="left")
        
        frame1 = await track.recv()
        timestamp1 = track._timestamp
        
        frame2 = await track.recv()
        timestamp2 = track._timestamp
        
        # Timestamp should increment by 90000/30 = 3000
        assert timestamp2 > timestamp1
        assert timestamp2 - timestamp1 == 3000
    
    @pytest.mark.asyncio
    async def test_camera_track_calls_get_frames(self, mock_stereo_camera, mock_video_frame):
        """Test that recv() calls stereo_cam.get_frames()"""
        from vr_server import CameraTrack
        
        track = CameraTrack(mock_stereo_camera, side="left")
        await track.recv()
        
        mock_stereo_camera.get_frames.assert_called_once()


class TestServoController:
    """Tests for servo controller functions"""
    
    @pytest.mark.asyncio
    async def test_connect_to_servo_controller_success(self):
        """Test successful connection to servo controller"""
        from vr_server import connect_to_servo_controller
        
        mock_reader = MagicMock()
        mock_writer = MagicMock()
        
        with patch('asyncio.open_connection', new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = (mock_reader, mock_writer)
            
            result = await connect_to_servo_controller(host='192.168.1.138', port=9090)
            
            assert result is True
            mock_connect.assert_called_once_with('192.168.1.138', 9090)
    
    @pytest.mark.asyncio
    async def test_connect_to_servo_controller_failure(self):
        """Test failed connection to servo controller"""
        from vr_server import connect_to_servo_controller
        
        with patch('asyncio.open_connection', new_callable=AsyncMock) as mock_connect:
            mock_connect.side_effect = ConnectionRefusedError("Connection refused")
            
            result = await connect_to_servo_controller(host='192.168.1.138', port=9090)
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_send_pose_to_servo_success(self):
        """Test sending pose data to servo controller"""
        import vr_server
        
        # Setup mock writer
        mock_writer = MagicMock()
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        vr_server.servo_writer = mock_writer
        
        pose_json = '{"type":"pose","position":{"x":0,"y":1,"z":0}}'
        
        await vr_server.send_pose_to_servo(pose_json)
        
        mock_writer.write.assert_called_once()
        call_args = mock_writer.write.call_args[0][0]
        assert call_args.decode('utf-8') == pose_json + '\n'
        mock_writer.drain.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_pose_to_servo_no_connection(self):
        """Test sending pose data when not connected"""
        import vr_server
        
        vr_server.servo_writer = None
        
        # Should not raise exception
        await vr_server.send_pose_to_servo('{"type":"pose"}')
    
    @pytest.mark.asyncio
    async def test_send_pose_to_servo_handles_error(self):
        """Test that send_pose_to_servo handles write errors"""
        import vr_server
        
        mock_writer = MagicMock()
        mock_writer.write.side_effect = Exception("Write error")
        vr_server.servo_writer = mock_writer
        
        # Should not raise exception
        await vr_server.send_pose_to_servo('{"type":"pose"}')
        
        # servo_writer should be reset to None
        assert vr_server.servo_writer is None


class TestWebRTCEndpoints:
    """Tests for WebRTC offer/answer endpoints"""
    
    @pytest.mark.asyncio
    async def test_offer_creates_peer_connection(self, mock_stereo_camera, mock_rtc_peer_connection, mock_video_frame):
        """Test that offer endpoint creates RTCPeerConnection"""
        from vr_server import offer
        
        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={})
        
        response = await offer(mock_request)
        
        assert mock_rtc_peer_connection.createDataChannel.called
        assert mock_rtc_peer_connection.addTransceiver.call_count == 2
        assert mock_rtc_peer_connection.createOffer.called
    
    @pytest.mark.asyncio
    async def test_offer_creates_data_channel(self, mock_stereo_camera, mock_rtc_peer_connection, mock_video_frame):
        """Test that offer creates data channel"""
        from vr_server import offer
        
        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={})
        
        await offer(mock_request)
        
        mock_rtc_peer_connection.createDataChannel.assert_called_once_with(
            "poseData", ordered=True, maxRetransmits=0
        )
    
    @pytest.mark.asyncio
    async def test_offer_adds_two_transceivers(self, mock_stereo_camera, mock_rtc_peer_connection, mock_video_frame):
        """Test that offer adds transceivers for left and right cameras"""
        from vr_server import offer
        
        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={})
        
        await offer(mock_request)
        
        # Should add two transceivers (left and right)
        assert mock_rtc_peer_connection.addTransceiver.call_count == 2
        
        # Both should be sendonly
        for call_obj in mock_rtc_peer_connection.addTransceiver.call_args_list:
            assert call_obj[1]['direction'] == 'sendonly'
    
    @pytest.mark.asyncio
    async def test_offer_returns_sdp(self, mock_stereo_camera, mock_rtc_peer_connection, mock_video_frame):
        """Test that offer returns SDP in response"""
        from vr_server import offer
        
        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={})
        
        response = await offer(mock_request)
        
        # Response should be a web.Response
        assert isinstance(response, web.Response)
        
        # Parse JSON body
        body = json.loads(response.body)
        assert 'sdp' in body
        assert 'type' in body
        assert body['type'] == 'offer'
    
    @pytest.mark.asyncio
    async def test_offer_sets_cors_headers(self, mock_stereo_camera, mock_rtc_peer_connection, mock_video_frame):
        """Test that offer response includes CORS headers"""
        from vr_server import offer
        
        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={})
        
        response = await offer(mock_request)
        
        assert response.headers['Access-Control-Allow-Origin'] == '*'
    
    @pytest.mark.asyncio
    async def test_answer_sets_remote_description(self, mock_stereo_camera, mock_rtc_peer_connection, mock_video_frame):
        """Test that answer endpoint sets remote description"""
        from vr_server import offer, answer
        import vr_server
        
        # First create an offer to set up _current_pc
        mock_offer_request = MagicMock()
        mock_offer_request.json = AsyncMock(return_value={})
        await offer(mock_offer_request)
        
        # Now send answer
        mock_answer_request = MagicMock()
        answer_sdp = {
            'sdp': 'v=0\r\no=- 789 012 IN IP4 0.0.0.0',
            'type': 'answer'
        }
        mock_answer_request.json = AsyncMock(return_value=answer_sdp)
        
        response = await answer(mock_answer_request)
        
        assert mock_rtc_peer_connection.setRemoteDescription.called
        body = json.loads(response.body)
        assert body['status'] == 'ok'
    
    @pytest.mark.asyncio
    async def test_answer_without_offer_returns_error(self, mock_stereo_camera):
        """Test that answer without prior offer returns error"""
        from vr_server import answer
        import vr_server
        
        # Reset _current_pc
        vr_server._current_pc = None
        
        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={'sdp': 'test', 'type': 'answer'})
        
        response = await answer(mock_request)
        
        body = json.loads(response.body)
        assert 'error' in body
    
    @pytest.mark.asyncio
    async def test_data_channel_message_handler(self, mock_stereo_camera, mock_rtc_peer_connection, mock_video_frame):
        """Test that data channel message handler forwards to servo"""
        from vr_server import offer
        import vr_server
        
        # Mock servo writer
        mock_writer = MagicMock()
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        vr_server.servo_writer = mock_writer
        
        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={})
        
        # Capture the message handler when @data_channel.on("message") is called
        message_handler_captured = None
        def capture_on_decorator(event_name):
            def decorator(func):
                nonlocal message_handler_captured
                if event_name == "message":
                    message_handler_captured = func
                return func
            return decorator
        
        data_channel = mock_rtc_peer_connection.createDataChannel.return_value
        data_channel.on = MagicMock(side_effect=capture_on_decorator)
        
        await offer(mock_request)
        
        # Simulate receiving a message through the captured handler
        if message_handler_captured:
            test_message = '{"type":"pose","position":{"x":0}}'
            message_handler_captured(test_message)
            
            # Give asyncio.create_task time to schedule
            await asyncio.sleep(0.01)


class TestCORSMiddleware:
    """Tests for CORS middleware"""
    
    @pytest.mark.asyncio
    async def test_cors_middleware_options_request(self):
        """Test CORS middleware handles OPTIONS requests"""
        from vr_server import cors_middleware
        
        mock_request = MagicMock()
        mock_request.method = "OPTIONS"
        mock_handler = AsyncMock()
        
        response = await cors_middleware(mock_request, mock_handler)
        
        assert response.headers['Access-Control-Allow-Origin'] == '*'
        assert 'Access-Control-Allow-Methods' in response.headers
        assert 'Access-Control-Allow-Headers' in response.headers
        mock_handler.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_cors_middleware_normal_request(self):
        """Test CORS middleware adds headers to normal requests"""
        from vr_server import cors_middleware
        
        mock_request = MagicMock()
        mock_request.method = "POST"
        
        mock_response = web.Response(text="OK")
        mock_handler = AsyncMock(return_value=mock_response)
        
        response = await cors_middleware(mock_request, mock_handler)
        
        assert response.headers['Access-Control-Allow-Origin'] == '*'
        mock_handler.assert_called_once_with(mock_request)


class TestApplicationLifecycle:
    """Tests for application startup and shutdown"""
    
    @pytest.mark.asyncio
    async def test_on_startup_connects_to_servo(self, mock_stereo_camera):
        """Test that on_startup connects to servo controller"""
        from vr_server import on_startup
        
        mock_app = MagicMock()
        
        with patch('vr_server.connect_to_servo_controller', new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = True
            
            await on_startup(mock_app)
            
            mock_connect.assert_called_once_with(host='192.168.1.138', port=9090)
    
    @pytest.mark.asyncio
    async def test_on_shutdown_closes_connections(self, mock_stereo_camera, mock_rtc_peer_connection):
        """Test that on_shutdown closes all connections"""
        from vr_server import on_shutdown
        import vr_server
        
        # Setup mock servo writer
        mock_writer = MagicMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()
        vr_server.servo_writer = mock_writer
        
        # Setup mock peer connections
        mock_pc1 = MagicMock()
        mock_pc1.close = AsyncMock()
        mock_pc2 = MagicMock()
        mock_pc2.close = AsyncMock()
        vr_server.pcs = {mock_pc1, mock_pc2}
        
        # Setup mock stereo_cam
        mock_cam = MagicMock()
        mock_cam.stop = MagicMock()
        vr_server.stereo_cam = mock_cam
        
        mock_app = MagicMock()
        await on_shutdown(mock_app)
        
        # Check servo writer closed
        mock_writer.close.assert_called_once()
        mock_writer.wait_closed.assert_called_once()
        
        # Check peer connections closed
        mock_pc1.close.assert_called_once()
        mock_pc2.close.assert_called_once()
        
        # Check camera stopped
        mock_cam.stop.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_on_shutdown_handles_no_servo(self, mock_stereo_camera):
        """Test that on_shutdown handles case with no servo connection"""
        from vr_server import on_shutdown
        import vr_server
        
        vr_server.servo_writer = None
        vr_server.pcs = set()
        
        mock_app = MagicMock()
        
        # Should not raise exception
        await on_shutdown(mock_app)


class TestIntegration:
    """Integration tests for complete workflows"""
    
    @pytest.mark.asyncio
    async def test_complete_webrtc_handshake(self, mock_stereo_camera, mock_rtc_peer_connection, mock_video_frame):
        """Test complete WebRTC offer/answer handshake"""
        from vr_server import offer, answer
        
        # Step 1: Client requests offer
        mock_offer_request = MagicMock()
        mock_offer_request.json = AsyncMock(return_value={})
        
        offer_response = await offer(mock_offer_request)
        offer_body = json.loads(offer_response.body)
        
        assert offer_body['type'] == 'offer'
        assert 'sdp' in offer_body
        
        # Step 2: Client sends answer
        mock_answer_request = MagicMock()
        mock_answer_request.json = AsyncMock(return_value={
            'sdp': 'v=0\r\no=- 789 012 IN IP4 0.0.0.0',
            'type': 'answer'
        })
        
        answer_response = await answer(mock_answer_request)
        answer_body = json.loads(answer_response.body)
        
        assert answer_body['status'] == 'ok'
        
        # Verify connection was established
        assert mock_rtc_peer_connection.setRemoteDescription.called
    
    @pytest.mark.asyncio
    async def test_camera_track_multiple_frames(self, mock_stereo_camera, mock_video_frame):
        """Test camera track can produce multiple frames"""
        from vr_server import CameraTrack
        
        track = CameraTrack(mock_stereo_camera, side="left")
        
        # Generate 10 frames
        for i in range(10):
            frame = await track.recv()
            assert frame is not None
        
        assert track.frame_count == 10
        assert mock_stereo_camera.get_frames.call_count == 10


# Run with: pytest test_vr_server.py -v
# Coverage: pytest test_vr_server.py --cov=vr_server --cov-report=html

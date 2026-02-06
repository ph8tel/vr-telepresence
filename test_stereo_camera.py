import pytest
import numpy as np
from unittest.mock import Mock, MagicMock, patch, PropertyMock
import cv2


@pytest.fixture
def mock_depthai():
    """Mock the depthai module and its components"""
    with patch('stereo_camera.dai') as mock_dai:
        # Create shared queues that we'll inject
        mock_queue_left = MagicMock()
        mock_queue_right = MagicMock()
        
        # Mock Pipeline
        mock_pipeline = MagicMock()
        mock_dai.Pipeline.return_value = mock_pipeline
        
        # Mock node creation - need to handle both Camera and StereoDepth
        def create_node_mock(node_type):
            mock_node = MagicMock()
            
            # The build() method needs to return different things based on node type
            if hasattr(node_type, '__name__') and node_type.__name__ == 'StereoDepth':
                # For StereoDepth, build() returns an object with rectified outputs
                mock_stereo_built = MagicMock()
                mock_stereo_built.rectifiedLeft.createOutputQueue.return_value = mock_queue_left
                mock_stereo_built.rectifiedRight.createOutputQueue.return_value = mock_queue_right
                mock_node.build.return_value = mock_stereo_built
            else:
                # For Camera, build() returns an object with requestFullResolutionOutput
                mock_camera_built = MagicMock()
                mock_node.build.return_value = mock_camera_built
            
            return mock_node
        
        mock_pipeline.create.side_effect = create_node_mock
        
        # Mock camera board sockets
        mock_dai.CameraBoardSocket.CAM_B = 'CAM_B'
        mock_dai.CameraBoardSocket.CAM_C = 'CAM_C'
        
        # Mock image frame type
        mock_dai.ImgFrame.Type.NV12 = 'NV12'
        
        # Mock node classes
        mock_dai.node.Camera = type('Camera', (), {'__name__': 'Camera'})
        mock_dai.node.StereoDepth = type('StereoDepth', (), {'__name__': 'StereoDepth'})
        mock_dai.node.StereoDepth.PresetMode = type('PresetMode', (), {'FAST_ACCURACY': 'FAST_ACCURACY'})()
        
        yield {
            'dai': mock_dai,
            'pipeline': mock_pipeline,
            'queue_left': mock_queue_left,
            'queue_right': mock_queue_right
        }


@pytest.fixture
def mock_frame_messages():
    """Create mock frame messages with getCvFrame() method that returns real numpy arrays"""
    def create_mock_message(width=1280, height=720):
        # Create a grayscale frame (single channel) - REAL numpy array
        frame = np.random.randint(0, 256, (height, width), dtype=np.uint8)
        
        # Create a simple object with getCvFrame method
        class MockMessage:
            def getCvFrame(self):
                return frame
        
        return MockMessage()
    
    return create_mock_message


class TestStereoCameraInit:
    """Tests for StereoCamera initialization"""
    
    def test_init_creates_pipeline(self, mock_depthai):
        """Test that pipeline is created on initialization"""
        from stereo_camera import StereoCamera
        
        camera = StereoCamera(size=(1280, 720))
        
        mock_depthai['dai'].Pipeline.assert_called_once()
        assert camera.size == (1280, 720)
    
    def test_init_starts_pipeline(self, mock_depthai):
        """Test that pipeline.start() is called"""
        from stereo_camera import StereoCamera
        
        camera = StereoCamera()
        
        mock_depthai['pipeline'].start.assert_called_once()
    
    def test_init_creates_camera_nodes(self, mock_depthai):
        """Test that left and right cameras are created with correct sockets"""
        from stereo_camera import StereoCamera
        
        camera = StereoCamera()
        
        # Should create multiple nodes (camera, stereo depth, etc.)
        assert mock_depthai['pipeline'].create.call_count >= 2
    
    def test_init_with_custom_size(self, mock_depthai):
        """Test initialization with custom resolution"""
        from stereo_camera import StereoCamera
        
        custom_size = (640, 480)
        camera = StereoCamera(size=custom_size)
        
        assert camera.size == custom_size


class TestStereoCameraGetFrames:
    """Tests for get_frames method"""
    
    def test_get_frames_returns_two_frames(self, mock_depthai, mock_frame_messages):
        """Test that get_frames returns left and right frames"""
        from stereo_camera import StereoCamera
        
        # Setup mock queues to return frames
        mock_depthai['queue_left'].get.return_value = mock_frame_messages()
        mock_depthai['queue_right'].get.return_value = mock_frame_messages()
        
        camera = StereoCamera()
        left, right = camera.get_frames()
        
        assert left is not None
        assert right is not None
        assert isinstance(left, np.ndarray)
        assert isinstance(right, np.ndarray)
    
    def test_get_frames_converts_to_rgb(self, mock_depthai, mock_frame_messages):
        """Test that frames are converted from grayscale to RGB"""
        from stereo_camera import StereoCamera
        
        mock_depthai['queue_left'].get.return_value = mock_frame_messages()
        mock_depthai['queue_right'].get.return_value = mock_frame_messages()
        
        camera = StereoCamera(size=(1280, 720))
        left, right = camera.get_frames()
        
        # RGB frames should have 3 channels
        assert left.shape[2] == 3
        assert right.shape[2] == 3
    
    def test_get_frames_correct_size(self, mock_depthai, mock_frame_messages):
        """Test that frames are resized to requested size"""
        from stereo_camera import StereoCamera
        
        mock_depthai['queue_left'].get.return_value = mock_frame_messages(width=1920, height=1080)
        mock_depthai['queue_right'].get.return_value = mock_frame_messages(width=1920, height=1080)
        
        requested_size = (640, 480)
        camera = StereoCamera(size=requested_size)
        left, right = camera.get_frames()
        
        assert left.shape[:2] == (requested_size[1], requested_size[0])
        assert right.shape[:2] == (requested_size[1], requested_size[0])
    
    def test_get_frames_no_resize_when_matching(self, mock_depthai, mock_frame_messages):
        """Test that frames are not resized when already correct size"""
        from stereo_camera import StereoCamera
        
        size = (1280, 720)
        mock_depthai['queue_left'].get.return_value = mock_frame_messages(width=size[0], height=size[1])
        mock_depthai['queue_right'].get.return_value = mock_frame_messages(width=size[0], height=size[1])
        
        camera = StereoCamera(size=size)
        left, right = camera.get_frames()
        
        assert left.shape[:2] == (size[1], size[0])
        assert right.shape[:2] == (size[1], size[0])
    
    def test_get_frames_pulls_from_both_queues(self, mock_depthai, mock_frame_messages):
        """Test that frames are pulled from both left and right queues"""
        from stereo_camera import StereoCamera
        
        mock_depthai['queue_left'].get.return_value = mock_frame_messages()
        mock_depthai['queue_right'].get.return_value = mock_frame_messages()
        
        camera = StereoCamera()
        camera.get_frames()
        
        mock_depthai['queue_left'].get.assert_called_once()
        mock_depthai['queue_right'].get.assert_called_once()


class TestStereoCameraGetStereoFrame:
    """Tests for get_stereo_frame method"""
    
    def test_get_stereo_frame_returns_concatenated(self, mock_depthai, mock_frame_messages):
        """Test that get_stereo_frame returns horizontally concatenated frames"""
        from stereo_camera import StereoCamera
        
        mock_depthai['queue_left'].get.return_value = mock_frame_messages()
        mock_depthai['queue_right'].get.return_value = mock_frame_messages()
        
        camera = StereoCamera(size=(1280, 720))
        stereo = camera.get_stereo_frame()
        
        # Concatenated frame should be double width
        assert stereo.shape[1] == 1280 * 2
        assert stereo.shape[0] == 720
    
    def test_get_stereo_frame_shape(self, mock_depthai, mock_frame_messages):
        """Test stereo frame has correct dimensions"""
        from stereo_camera import StereoCamera
        
        size = (640, 480)
        mock_depthai['queue_left'].get.return_value = mock_frame_messages(width=size[0], height=size[1])
        mock_depthai['queue_right'].get.return_value = mock_frame_messages(width=size[0], height=size[1])
        
        camera = StereoCamera(size=size)
        stereo = camera.get_stereo_frame()
        
        expected_width = size[0] * 2
        expected_height = size[1]
        assert stereo.shape == (expected_height, expected_width, 3)


class TestStereoCameraStop:
    """Tests for stop method"""
    
    def test_stop_calls_pipeline_stop(self, mock_depthai):
        """Test that stop() calls pipeline.stop()"""
        from stereo_camera import StereoCamera
        
        camera = StereoCamera()
        camera.stop()
        
        mock_depthai['pipeline'].stop.assert_called_once()
    
    def test_stop_handles_exception(self, mock_depthai):
        """Test that stop() handles exceptions gracefully"""
        from stereo_camera import StereoCamera
        
        mock_depthai['pipeline'].stop.side_effect = Exception("Hardware error")
        
        camera = StereoCamera()
        # Should not raise exception
        camera.stop()


class TestStereoCameraCache:
    """Tests for caching methods"""
    
    def test_get_frames_once_caches_result(self, mock_depthai, mock_frame_messages):
        """Test that get_frames_once caches the result"""
        from stereo_camera import StereoCamera
        
        mock_depthai['queue_left'].get.return_value = mock_frame_messages()
        mock_depthai['queue_right'].get.return_value = mock_frame_messages()
        
        camera = StereoCamera()
        
        # First call should fetch from hardware
        left1, right1 = camera.get_frames_once()
        
        # Second call should return cached value
        left2, right2 = camera.get_frames_once()
        
        # Queue should only be called once (for the first call)
        assert mock_depthai['queue_left'].get.call_count == 1
        assert mock_depthai['queue_right'].get.call_count == 1
        
        # Results should be identical (same object reference)
        assert left1 is left2
        assert right1 is right2
    
    def test_clear_cache_removes_cached_frames(self, mock_depthai, mock_frame_messages):
        """Test that clear_cache removes cached frames"""
        from stereo_camera import StereoCamera
        
        mock_depthai['queue_left'].get.return_value = mock_frame_messages()
        mock_depthai['queue_right'].get.return_value = mock_frame_messages()
        
        camera = StereoCamera()
        
        # Cache frames
        camera.get_frames_once()
        assert hasattr(camera, '_cached')
        
        # Clear cache
        camera.clear_cache()
        assert not hasattr(camera, '_cached')
    
    def test_get_frames_once_after_clear_refetches(self, mock_depthai, mock_frame_messages):
        """Test that get_frames_once refetches after clear_cache"""
        from stereo_camera import StereoCamera
        
        mock_depthai['queue_left'].get.return_value = mock_frame_messages()
        mock_depthai['queue_right'].get.return_value = mock_frame_messages()
        
        camera = StereoCamera()
        
        # First fetch
        camera.get_frames_once()
        assert mock_depthai['queue_left'].get.call_count == 1
        
        # Clear cache
        camera.clear_cache()
        
        # Second fetch should hit hardware again
        camera.get_frames_once()
        assert mock_depthai['queue_left'].get.call_count == 2
    
    def test_clear_cache_when_no_cache_exists(self, mock_depthai):
        """Test that clear_cache doesn't fail when no cache exists"""
        from stereo_camera import StereoCamera
        
        camera = StereoCamera()
        
        # Should not raise exception
        camera.clear_cache()


class TestStereoCameraIntegration:
    """Integration tests for StereoCamera"""
    
    def test_multiple_frame_captures(self, mock_depthai, mock_frame_messages):
        """Test multiple consecutive frame captures"""
        from stereo_camera import StereoCamera
        
        mock_depthai['queue_left'].get.return_value = mock_frame_messages()
        mock_depthai['queue_right'].get.return_value = mock_frame_messages()
        
        camera = StereoCamera()
        
        # Capture multiple frames
        for i in range(5):
            left, right = camera.get_frames()
            assert left.shape[2] == 3
            assert right.shape[2] == 3
        
        # Should have called get() 5 times for each queue
        assert mock_depthai['queue_left'].get.call_count == 5
        assert mock_depthai['queue_right'].get.call_count == 5
    
    def test_lifecycle(self, mock_depthai, mock_frame_messages):
        """Test complete lifecycle: init -> capture -> stop"""
        from stereo_camera import StereoCamera
        
        mock_depthai['queue_left'].get.return_value = mock_frame_messages()
        mock_depthai['queue_right'].get.return_value = mock_frame_messages()
        
        # Initialize
        camera = StereoCamera(size=(1280, 720))
        assert mock_depthai['pipeline'].start.called
        
        # Capture frames
        left, right = camera.get_frames()
        assert left is not None
        assert right is not None
        
        # Get stereo frame
        stereo = camera.get_stereo_frame()
        assert stereo.shape[1] == 1280 * 2
        
        # Stop
        camera.stop()
        assert mock_depthai['pipeline'].stop.called


# Run tests with: pytest test_stereo_camera.py -v

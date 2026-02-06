# VR Stereo Streaming System

Real-time stereo camera streaming from OAK-Pro camera to VR headsets using WebXR and WebRTC.

## Overview

This system streams synchronized stereo video from a DepthAI OAK-Pro camera (connected to Raspberry Pi 5) to VR headsets like Meta Quest Pro over WebRTC, with bidirectional pose/controller data transmission.

**Key Features:**
- **Stereo video streaming** at 1280x720@30fps per eye
- **WebXR integration** for native VR headset rendering
- **IPD compensation** via WebGL shader adjustment (71mm user IPD vs 75mm camera baseline)
- **Real-time pose tracking** - head position/orientation sent every frame
- **Controller input** - joystick and button data forwarded to optional servo controller
- **Hardware-synchronized stereo** - rectified stereo pairs from OAK-Pro StereoDepth node

## Architecture

```
┌─────────────┐    USB    ┌──────────────┐   WebRTC    ┌──────────────┐
│  OAK-Pro    │◄─────────►│ Raspberry    │◄───────────►│  Meta Quest  │
│  Camera     │           │ Pi 5         │   (HTTPS)   │  Pro         │
│ (CAM_B/C)   │           │ (vr_server)  │             │ (index.html) │
└─────────────┘           └──────┬───────┘             └──────────────┘
                                 │ TCP
                                 │ (optional)
                          ┌──────▼───────┐
                          │ Raspberry    │
                          │ Pi 4         │
                          │ (Servo Ctrl) │
                          └──────────────┘
```

### Components

1. **[stereo_camera.py](stereo_camera.py)** - OAK-Pro camera interface
   - Manages DepthAI pipeline for stereo rectification
   - Outputs synchronized RGB frames from left (CAM_B) and right (CAM_C) cameras

2. **[vr_server.py](vr_server.py)** - WebRTC signaling server
   - aiohttp web server on port 8080
   - Creates WebRTC offer with 2 video tracks + data channel
   - Forwards pose/controller data to Pi 4 servo controller (optional)

3. **[index.html](index.html)** - WebXR VR client
   - Runs in Meta Quest Browser
   - Renders stereo video via WebGL with IPD correction
   - Sends head tracking and controller inputs back to server

## Hardware Requirements

- **Raspberry Pi 5** (4GB+ RAM recommended)
- **OAK-Pro camera** (Luxonis DepthAI with stereo cameras)
- **Meta Quest Pro** or other WebXR-compatible headset
- **Network** - Both Pi and headset on same network or via Cloudflare Tunnel
- *(Optional)* Raspberry Pi 4 for servo control

## Software Requirements

- Python 3.9+
- Modern browser with WebXR support (Meta Quest Browser recommended)
- HTTPS endpoint (WebXR requires secure context)

## Installation

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Network Access

**Option A: Local Network (Testing)**
```bash
# Find Pi's IP address
hostname -I

# Access from Quest Browser: http://<pi-ip>:8080
# Note: WebXR may require HTTPS even on local network
```

**Option B: Cloudflare Tunnel (Recommended)**
```bash
# Install cloudflared
# Configure tunnel to expose localhost:8080

# Access via: https://<your-tunnel>.trycloudflare.com
```

### 3. (Optional) Configure Servo Controller

Edit [vr_server.py](vr_server.py) line 159:
```python
await connect_to_servo_controller(host='192.168.1.138', port=9090)
```

## Usage

### Start the Server

```bash
# On Raspberry Pi 5 with OAK-Pro connected
python3 vr_server.py
```

Expected output:
```
StereoCamera initialized with OAK-Pro (rectified stereo for VR)
Attempting to connect to servo controller at 192.168.1.138:9090...
Starting HTTP server on port 8080 (Cloudflare Tunnel provides HTTPS)
```

### Access from VR Headset

1. Open **Meta Quest Browser** (not Wolvic - WebXR not supported)
2. Navigate to your server URL (e.g., `https://your-tunnel.trycloudflare.com`)
3. Click **"Enter VR"** button
4. Grant camera/WebXR permissions if prompted

### Testing Without VR

For debugging video streams on desktop:
```bash
# Open in any browser
http://<pi-ip>:8080

# Click "Test View (No VR)" to see side-by-side stereo streams
# Check debug log panel for WebRTC connection status
```

## Configuration

### Video Quality

Adjust resolution in [vr_server.py](vr_server.py):
```python
stereo_cam = StereoCamera(size=(1280, 720))  # Change to (640, 480) for lower bandwidth
```

Adjust frame rate in [vr_server.py](vr_server.py):
```python
await asyncio.sleep(1/30)  # Change to 1/15 for 15fps
```

### IPD Adjustment

If user IPD differs from 71mm, edit [index.html](index.html) line ~284:
```javascript
const ipdAdjustment = 0.0267;  // Formula: (camera_baseline - user_ipd) / camera_baseline / 2
                                // Example: (75mm - 71mm) / 75mm / 2 = 0.0267
```

### Controller Mappings

Edit `sendControllerData()` in [index.html](index.html) lines 497-562:
```javascript
// Quest Pro button indices:
// 0 = Trigger
// 1 = Grip
// 4 = A/X button
// 5 = B/Y button
```

## Troubleshooting

### No Video in VR Headset

1. Check browser console for WebRTC errors
2. Verify both video tracks added: look for "Added tracks via transceivers" in server logs
3. Check ICE connection state in debug log panel
4. Ensure HTTPS is used (WebXR requirement)

### Data Channel Not Opening

1. Check SDP includes `m=application` line (logged during signaling)
2. Verify server creates data channel before creating offer
3. Look for "Data channel opened" in browser debug log

### Frame Drops

1. Reduce resolution: `size=(640, 480)`
2. Lower frame rate: `await asyncio.sleep(1/20)` for 20fps
3. Adjust queue size in [stereo_camera.py](stereo_camera.py): `maxSize=2`

### WebXR Not Available

**Symptoms:** "navigator.xr is undefined"

**Solutions:**
- Use Meta Quest Browser (built-in), not Wolvic
- Ensure page served via HTTPS
- Check browser supports WebXR: visit https://immersiveweb.dev/

## Development

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-cov

# Run all tests
pytest test_stereo_camera.py test_vr_server.py -v

# Run specific test class
pytest test_stereo_camera.py::TestStereoCameraInit -v

# Generate coverage report
pytest test_stereo_camera.py test_vr_server.py --cov=stereo_camera --cov=vr_server --cov-report=html
```

### Test Suite Overview

The project includes 48 comprehensive unit tests across two test files:

- **test_stereo_camera.py** (19 tests) - Tests for OAK-Pro camera interface
- **test_vr_server.py** (29 tests) - Tests for WebRTC server and async operations

All tests are fully isolated from hardware dependencies using mocks, allowing tests to run on any machine without an OAK-Pro camera or active network connections.

### Understanding the Mock Strategy

#### Why Mocking is Essential

This system has deep hardware dependencies that make testing challenging:

1. **OAK-Pro camera** - Requires USB-connected hardware (`depthai` module)
2. **WebRTC connections** - Requires network peers and async operations
3. **Servo controller** - Requires TCP connection to external Pi 4
4. **OpenCV video processing** - Requires real numpy arrays with specific shapes

Without mocking, tests would:
- Fail on machines without OAK-Pro camera
- Require complex network setup
- Run slowly due to hardware I/O
- Be non-deterministic (network timing issues)

#### Mock Patterns Used

**1. DepthAI Pipeline Mocking (test_stereo_camera.py)**

The DepthAI API uses a builder pattern that requires multi-level mocking:

```python
# Real code:
left = pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_B)
stereo = pipeline.create(dai.node.StereoDepth).build(left=left_out, right=right_out)
```

**Challenge:** The `.create().build()` chain returns different objects at each level.

**Solution:** Create a mock chain with proper return values:

```python
@pytest.fixture
def mock_depthai():
    with patch('stereo_camera.dai') as mock_dai:
        # Mock pipeline
        mock_pipeline = MagicMock()
        mock_dai.Pipeline.return_value = mock_pipeline
        
        # Mock camera nodes with .build() chain
        mock_camera_node = MagicMock()
        mock_camera_built = MagicMock()
        mock_camera_built.requestFullResolutionOutput.return_value = MagicMock()
        mock_camera_node.build.return_value = mock_camera_built
        
        # Mock stereo node with output queues
        mock_stereo_node = MagicMock()
        mock_stereo_built = MagicMock()
        mock_stereo_built.rectifiedLeft.createOutputQueue.return_value = MagicMock()
        mock_stereo_built.rectifiedRight.createOutputQueue.return_value = MagicMock()
        mock_stereo_node.build.return_value = mock_stereo_built
        
        # Return appropriate mock based on node type
        def create_node(node_type):
            if node_type == mock_dai.node.Camera:
                return mock_camera_node
            elif node_type == mock_dai.node.StereoDepth:
                return mock_stereo_node
        
        mock_pipeline.create.side_effect = create_node
        yield mock_dai
```

**Key insight:** Each `.build()` call must return a mock with the next level's methods.

**2. Frame Data Mocking**

**Challenge:** `getCvFrame()` must return actual numpy arrays (not MagicMock) because OpenCV operations like `cv2.cvtColor()` require real array objects.

**Solution:** Create a custom class that returns real numpy arrays:

```python
class MockMessage:
    """Mock for DepthAI frame messages that returns real numpy arrays"""
    def getCvFrame(self):
        # Return actual grayscale image (simulating OAK-Pro output)
        return np.zeros((720, 1280), dtype=np.uint8)

# Use in queue mocks
mock_queue.get.return_value = MockMessage()
```

**Why this works:** 
- `np.zeros()` creates a real numpy array
- OpenCV operations work correctly
- Tests verify shape/type transformations (grayscale→RGB, resizing)

**3. Async WebRTC Mocking (test_vr_server.py)**

**Challenge:** aiortc creates peer connections and tracks that involve async operations.

**Solution:** Use `AsyncMock` for async methods and mock the entire WebRTC stack:

```python
@pytest.fixture
def mock_rtc_peer_connection():
    with patch('vr_server.RTCPeerConnection') as mock_rtc:
        mock_pc = MagicMock()
        mock_pc.createOffer = AsyncMock(return_value=MagicMock(sdp="offer", type="offer"))
        mock_pc.setLocalDescription = AsyncMock()
        mock_pc.setRemoteDescription = AsyncMock()
        mock_pc.createDataChannel.return_value = MagicMock()
        mock_rtc.return_value = mock_pc
        yield mock_rtc
```

**4. Data Channel Decorator Mocking**

**Challenge:** The data channel uses Python decorators for event handlers:

```python
@data_channel.on("message")
def on_message(msg):
    # Handle message
```

**Standard mock approach fails:** `data_channel.on.call_args_list` doesn't capture the decorated function.

**Solution:** Mock `on()` to return a decorator that captures the handler:

```python
message_handler_captured = None

def capture_on_decorator(event_name):
    def decorator(func):
        nonlocal message_handler_captured
        if event_name == "message":
            message_handler_captured = func
        return func
    return decorator

data_channel.on = MagicMock(side_effect=capture_on_decorator)

# Later: call the captured handler to test it
message_handler_captured('{"type":"pose","x":1}')
```

**5. Module-Level Code Isolation**

**Challenge:** `vr_server.py` has module-level instantiation:

```python
stereo_cam = StereoCamera()  # Runs when imported!
```

This causes "No available devices" error during test import.

**Solution A:** Guard execution in source file:

```python
# In vr_server.py
if __name__ == "__main__":
    web.run_app(app, port=8080)  # Only run when executed directly
```

**Solution B:** Mock before import in tests:

```python
with patch('stereo_camera.StereoCamera'):
    import vr_server
```

**6. VideoFrame Mocking**

**Challenge:** `av.VideoFrame.from_ndarray()` is called inside CameraTrack.recv()

**Solution:** Mock the av module and return a mock frame with required attributes:

```python
@pytest.fixture
def mock_video_frame():
    with patch('av.VideoFrame') as mock_vf:
        mock_frame = MagicMock()
        mock_frame.pts = 0
        mock_frame.time_base = fractions.Fraction(1, 90000)
        mock_vf.from_ndarray.return_value = mock_frame
        yield mock_vf
```

### Testing Best Practices

**When adding new tests:**

1. **Identify hardware dependencies** - What external systems does the code touch?
2. **Mock at the boundary** - Mock external libraries (depthai, aiortc), not your own code
3. **Return realistic data** - Use real numpy arrays, not MagicMock objects
4. **Test behavior, not implementation** - Verify outputs and side effects, not internal calls
5. **Use pytest fixtures** - Share common mocks across test classes

**Common pitfalls:**

- ❌ `mock_queue.get.return_value = MagicMock()` → OpenCV fails on MagicMock
- ✅ `mock_queue.get.return_value = MockMessage()` → Returns real numpy array

- ❌ Mocking your own functions → Tests become tautological
- ✅ Mocking external libraries → Tests verify your integration logic

- ❌ Global mocks in module scope → Leaks between test files
- ✅ Fixtures with context managers → Proper isolation

### Debug Logging

Server logs show:
- WebRTC connection states
- Track creation and negotiation
- Data channel messages (first 100 chars)
- Servo controller connection status

Client logs (in browser and debug panel) show:
- ICE/connection states
- Video track readiness
- Pose data transmission rate
- Controller input events

## Protocol Specifications

### WebRTC Data Channel Messages

All messages are JSON with `type` discriminator:

**Pose data (sent every frame, 72-120Hz):**
```json
{
  "type": "pose",
  "timestamp": 1234567890,
  "position": {"x": 0.0, "y": 1.6, "z": 0.0},
  "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}
}
```

**Controller data (sent every 3rd frame, ~24-40Hz):**
```json
{
  "type": "controller",
  "timestamp": 1234567890,
  "leftJoystick": {"x": 0.0, "y": 0.0},
  "rightJoystick": {"x": 0.0, "y": 0.0},
  "buttons": {
    "left_trigger": true,
    "plow_up": true
  }
}
```

## Why This Architecture?

**Q: Why does server create the WebRTC offer?**  
A: Server is the media source (sendonly tracks), so it must create the offer with tracks already added.

**Q: Why rectify stereo images?**  
A: Raw stereo would show vertically misaligned images causing eye strain. StereoDepth node ensures perfect alignment.

**Q: Why use data channel in offer?**  
A: Ensures negotiation completes before client tries to send pose data, avoiding race conditions.

**Q: Why TCP for servo control?**  
A: Servo commands need reliability (guaranteed delivery) not speed. Video uses WebRTC's UDP for low latency.

**Q: Why manual PTS timestamps?**  
A: aiortc requires monotonic presentation timestamps for proper video encoding.

## License

MIT

## Contributing

See [.github/copilot-instructions.md](.github/copilot-instructions.md) for development guidelines and architecture details.

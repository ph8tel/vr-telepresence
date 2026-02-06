import asyncio
import json
import cv2
import numpy as np
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiohttp import web
from stereo_camera import StereoCamera
import av
import time


class StereoStreamTrack(VideoStreamTrack):
    kind = "video"

    def __init__(self, camera, eye):
        super().__init__()
        self.camera = camera
        self.eye = eye  # "left" or "right"

    async def recv(self):
        frame_left, frame_right = self.camera.get_frames()

        if frame_left is None:
            await asyncio.sleep(0.001)
            return await self.recv()

        frame = frame_left if self.eye == "left" else frame_right

        # Convert RGB → BGR for OpenCV → then to VideoFrame
        bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        video_frame = av.VideoFrame.from_ndarray(bgr, format="bgr24")
        video_frame.pts = time.time_ns() // 1000
        video_frame.time_base = 1 / 1_000_000

        return video_frame


async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()

    # Create camera
    camera = StereoCamera()
    camera.start()

    # Add left and right tracks
    pc.addTrack(StereoStreamTrack(camera, "left"))
    pc.addTrack(StereoStreamTrack(camera, "right"))

    @pc.on("iceconnectionstatechange")
    def on_ice_state_change():
        if pc.iceConnectionState == "failed":
            camera.stop()

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        ),
    )


app = web.Application()
app.router.add_post("/offer", offer)

if __name__ == "__main__":
    web.run_app(app, port=8080)
import json
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.frames.frames import MetricsFrame, OutputTransportMessageFrame
from pipecat.processors.metrics.frame_processor_metrics import TTFBMetricsData

class TTFBProcessor(FrameProcessor):
    """Intercepts TTFB metrics from the pipeline and sends them to the client UI."""
    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        
        if isinstance(frame, MetricsFrame):
            for metric in frame.data:
                if isinstance(metric, TTFBMetricsData):
                    # Send custom App Message to the client
                    msg = {"type": "ttfb", "value": round(metric.value, 2)}
                    await self.push_frame(
                        OutputTransportMessageFrame(message=msg), direction
                    )

        await self.push_frame(frame, direction)

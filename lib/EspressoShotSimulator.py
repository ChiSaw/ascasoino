import time
import random


class EspressoShotSimulator:
    def __init__(self, target_weight=30.0, shot_time=28.0):
        self.target_weight = target_weight
        self.shot_time = shot_time
        self.current_weight = 0.0
        self.start_time = None
        self.is_running = False

        # Different stages of the espresso shot with corresponding durations and flow rates
        self.stages = [
            {"name": "Pre-Infusion", "duration": 8.0, "flow_rate": 0.0},  # Pre-infusion time (no flow)
            {"name": "Slow Flow", "duration": 4.0, "flow_rate": 0.5},  # Initial slow flow
            {"name": "Main Extraction", "duration": 15.0, "flow_rate": 2.2},  # Main extraction phase (higher flow rate)
            {"name": "Slow Down", "duration": 2.0, "flow_rate": 0.4},  # Slow down phase (reducing flow rate)
            {"name": "Dripping", "duration": 1.0, "flow_rate": 0.1},  # Dripping phase (low flow rate)
        ]

    def start_shot(self):
        self.start_time = time.time()
        self.is_running = True

    def stop_shot(self):
        self.is_running = False

    def get_current_weight(self):
        if self.is_running:
            elapsed_time = time.time() - self.start_time
            total_time = sum(stage["duration"] for stage in self.stages)

            if elapsed_time >= total_time:
                self.stop_shot()
                return self.target_weight

            current_stage = None
            evaluated_time = 0
            self.current_weight = 0.0
            for stage in self.stages:
                if elapsed_time < (evaluated_time + stage["duration"]):
                    current_stage = stage
                    print(f"{current_stage['name']}")
                    break
                evaluated_time += stage["duration"]
                self.current_weight += stage["duration"] * stage["flow_rate"] + random.uniform(0, 0.1)
            time_in_stage = elapsed_time - evaluated_time

            if current_stage:
                self.current_weight += current_stage["flow_rate"] * time_in_stage
                if self.current_weight < 0:
                    self.current_weight = 0
                return self.current_weight + random.uniform(0, 0.1)
            else:
                return self.current_weight
        else:
            return self.current_weight

    def get_current_time(self):
        if self.is_running:
            return time.time() - self.start_time
        elif self.start_time is not None:
            return self.stop_time - self.start_time
        else:
            return 0.0

# context_manager.py

def build_behavior_profile(relationship, emotion):
    return {
        "relationship": relationship,
        "emotion": emotion
    }

class ContextManager:
    def __init__(self, config, emotion, profile, relationship):
        self.config = config
        self.emotion = emotion
        self.profile = profile
        self.relationship = relationship

    def update(self, emotion, profile, relationship):
        self.emotion = emotion
        self.profile = profile
        self.relationship = relationship
    def update_emotion(self, emotion):
        self.emotion = emotion

    def update_profile(self, profile):
        self.profile = profile

    def update_relationship(self, relationship):
        self.relationship = relationship
    def get_behavior(self):
        return build_behavior_profile(self.relationship, self.emotion)
    def get_context(self):
        return {
            "config": self.config,
            "emotion": self.emotion,
            "profile": self.profile,
            "relationship": self.relationship
        }
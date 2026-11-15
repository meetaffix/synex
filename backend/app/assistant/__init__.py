"""Synex assistant: a voice and text agent on Deepgram's Voice Agent API.

Everything the agent can do goes through ``registry`` (typed tools, permission checks, audit log). Write
tools only ever create a proposal; applying one needs the user's click (``registry.confirm_proposal``).
"""

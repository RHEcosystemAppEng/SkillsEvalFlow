/**
 * Custom response parser for the Lightspeed A2A JSON-RPC response.
 * Handles cases where artifacts may not be present yet (state: "working").
 */
module.exports = function (json) {
  const result = json.result || {};
  
  // Try artifacts first
  const artifacts = result.artifacts || [];
  for (const artifact of artifacts) {
    const parts = artifact.parts || [];
    for (const part of parts) {
      if (part.kind === 'text' && !(part.metadata && part.metadata.adk_thought)) {
        return part.text;
      }
    }
  }
  
  // Fall back to history (last agent message)
  const history = result.history || [];
  for (let i = history.length - 1; i >= 0; i--) {
    const msg = history[i];
    if (msg.role === 'agent') {
      const parts = msg.parts || [];
      for (const part of parts) {
        if (part.kind === 'text' && !(part.metadata && part.metadata.adk_thought)) {
          return part.text;
        }
      }
    }
  }
  
  // Fall back to status message
  const statusMsg = (result.status || {}).message || {};
  const statusParts = statusMsg.parts || [];
  for (const part of statusParts) {
    if (part.kind === 'text') {
      return part.text;
    }
  }
  
  return `[No response text - state: ${(result.status || {}).state || 'unknown'}]`;
};

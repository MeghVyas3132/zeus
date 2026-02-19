import errorEnvelopeSchema from "../schemas/error-envelope.schema.json";
import runAgentRequestSchema from "../schemas/run-agent-request.schema.json";
import runAgentResponseSchema from "../schemas/run-agent-response.schema.json";
import runAgentDuplicateResponseSchema from "../schemas/run-agent-duplicate-response.schema.json";
import resultsSchema from "../schemas/results.schema.json";
import thoughtEventSchema from "../schemas/socket-thought-event.schema.json";
import fixAppliedEventSchema from "../schemas/socket-fix-applied.schema.json";
import ciUpdateEventSchema from "../schemas/socket-ci-update.schema.json";
import telemetryTickEventSchema from "../schemas/socket-telemetry-tick.schema.json";
import runCompleteEventSchema from "../schemas/socket-run-complete.schema.json";

export * from "./types.js";

export const schemas = {
  errorEnvelopeSchema,
  runAgentRequestSchema,
  runAgentResponseSchema,
  runAgentDuplicateResponseSchema,
  resultsSchema,
  thoughtEventSchema,
  fixAppliedEventSchema,
  ciUpdateEventSchema,
  telemetryTickEventSchema,
  runCompleteEventSchema
};

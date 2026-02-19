import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import type { RequestHandler } from "express";
import runAgentRequestSchema from "@rift/contracts/schemas/run-agent-request.schema.json" with { type: "json" };
import runAgentResponseSchema from "@rift/contracts/schemas/run-agent-response.schema.json" with { type: "json" };
import runAgentDuplicateResponseSchema from "@rift/contracts/schemas/run-agent-duplicate-response.schema.json" with { type: "json" };
import resultsSchema from "@rift/contracts/schemas/results.schema.json" with { type: "json" };
import thoughtEventSchema from "@rift/contracts/schemas/socket-thought-event.schema.json" with { type: "json" };
import fixAppliedEventSchema from "@rift/contracts/schemas/socket-fix-applied.schema.json" with { type: "json" };
import ciUpdateEventSchema from "@rift/contracts/schemas/socket-ci-update.schema.json" with { type: "json" };
import telemetryTickEventSchema from "@rift/contracts/schemas/socket-telemetry-tick.schema.json" with { type: "json" };
import runCompleteEventSchema from "@rift/contracts/schemas/socket-run-complete.schema.json" with { type: "json" };
import { buildErrorEnvelope } from "./error-envelope.js";

// @ts-ignore -- CJS default export interop under NodeNext
const ajv = new Ajv2020({ allErrors: true, strict: true });
// @ts-ignore -- CJS default export interop under NodeNext
addFormats(ajv);

const validators = {
  runAgentRequest: ajv.compile(runAgentRequestSchema),
  runAgentResponse: ajv.compile(runAgentResponseSchema),
  runAgentDuplicateResponse: ajv.compile(runAgentDuplicateResponseSchema),
  results: ajv.compile(resultsSchema),
  thoughtEvent: ajv.compile(thoughtEventSchema),
  fixAppliedEvent: ajv.compile(fixAppliedEventSchema),
  ciUpdateEvent: ajv.compile(ciUpdateEventSchema),
  telemetryTickEvent: ajv.compile(telemetryTickEventSchema),
  runCompleteEvent: ajv.compile(runCompleteEventSchema)
};

export function validateBody<K extends keyof typeof validators>(key: K): RequestHandler {
  return (req, res, next) => {
    const validate = validators[key];
    if (validate(req.body)) {
      return next();
    }

    return res.status(400).json(
      buildErrorEnvelope("INVALID_INPUT", "Request payload validation failed", {
        schema: key,
        errors: validate.errors ?? []
      })
    );
  };
}

export const schemaValidators = validators;

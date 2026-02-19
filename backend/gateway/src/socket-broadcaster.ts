import type {
  CiUpdateEvent,
  FixAppliedEvent,
  RunCompleteEvent,
  ThoughtEvent,
  TelemetryTickEvent
} from "@rift/contracts";
import { schemaValidators } from "./validators.js";

export interface SocketLike {
  to(room: string): {
    emit(event: string, payload: unknown): void;
  };
}

export class ContractSafeBroadcaster {
  constructor(private readonly io: SocketLike) {}

  emitThought(room: string, payload: ThoughtEvent): void {
    if (!schemaValidators.thoughtEvent(payload)) {
      throw new Error("Invalid thought_event payload");
    }
    this.io.to(room).emit("thought_event", payload);
  }

  emitFixApplied(room: string, payload: FixAppliedEvent): void {
    if (!schemaValidators.fixAppliedEvent(payload)) {
      throw new Error("Invalid fix_applied payload");
    }
    this.io.to(room).emit("fix_applied", payload);
  }

  emitCiUpdate(room: string, payload: CiUpdateEvent): void {
    if (!schemaValidators.ciUpdateEvent(payload)) {
      throw new Error("Invalid ci_update payload");
    }
    this.io.to(room).emit("ci_update", payload);
  }

  emitTelemetryTick(room: string, payload: TelemetryTickEvent): void {
    if (!schemaValidators.telemetryTickEvent(payload)) {
      throw new Error("Invalid telemetry_tick payload");
    }
    this.io.to(room).emit("telemetry_tick", payload);
  }

  emitRunComplete(room: string, payload: RunCompleteEvent): void {
    if (!schemaValidators.runCompleteEvent(payload)) {
      throw new Error("Invalid run_complete payload");
    }
    this.io.to(room).emit("run_complete", payload);
  }
}

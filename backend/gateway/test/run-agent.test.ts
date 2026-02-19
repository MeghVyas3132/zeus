import request from "supertest";
import { describe, expect, it } from "vitest";
import { createApp } from "../src/app.js";
import { runStore } from "../src/run-store.js";

describe("POST /run-agent", () => {
  const app = createApp();

  it("returns 400 envelope for invalid payload", async () => {
    const response = await request(app).post("/run-agent").send({ repo_url: "invalid" });

    expect(response.status).toBe(400);
    expect(response.body.error.code).toBe("INVALID_INPUT");
    expect(response.body.error.message).toBe("Request payload validation failed");
  });

  it("returns queued response for valid payload", async () => {
    const response = await request(app)
      .post("/run-agent")
      .send({
        repo_url: "https://github.com/org/repo",
        team_name: "RIFT ORGANISERS",
        leader_name: "Saiyam Kumar"
      });

    expect(response.status).toBe(202);
    expect(response.body.status).toBe("queued");
    expect(response.body.branch_name).toBe("RIFT_ORGANISERS_SAIYAM_KUMAR_AI_Fix");
    expect(response.body.socket_room).toMatch(/^\/run\//);
    expect(response.body.fingerprint).toMatch(/^[a-f0-9]{64}$/);

    runStore.markComplete(response.body.run_id);
  });

  it("returns 409 for duplicate active submission fingerprint", async () => {
    const payload = {
      repo_url: "https://github.com/org/repo",
      team_name: "RIFT ORGANISERS",
      leader_name: "Saiyam Kumar"
    };

    const first = await request(app).post("/run-agent").send(payload);
    expect(first.status).toBe(202);

    const second = await request(app).post("/run-agent").send(payload);
    expect(second.status).toBe(409);
    expect(second.body.run_id).toBe(first.body.run_id);
    expect(second.body.status).toBe("queued");
    expect(second.body.message).toBe("Active run already exists for this submission fingerprint");

    runStore.markComplete(first.body.run_id);
  });
});

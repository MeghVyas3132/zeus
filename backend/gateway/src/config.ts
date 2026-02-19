import path from "node:path";

export const config = {
  port: Number(process.env.PORT ?? 3000),
  outputsDir: process.env.OUTPUTS_DIR ?? path.resolve(process.cwd(), "outputs"),
  maxIterations: Number(process.env.MAX_ITERATIONS ?? 5)
};

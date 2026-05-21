// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 VECTOR - Altaire Limited
import { beforeEach, describe, expect, it, vi } from "vitest";

// ── Mocks ────────────────────────────────────────────────────────────────
// All external service dependencies are mocked so these tests run without Docker.

vi.mock("../../src/services/docker.js", () => ({
  isDockerAvailable: vi.fn(),
  isQdrantRunning: vi.fn(),
}));

vi.mock("../../src/services/qdrant.js", () => ({
  listCodebaseCollections: vi.fn(),
}));

vi.mock("../../src/services/indexer.js", () => ({
  getPersistedIndexingStatus: vi.fn(),
  indexProject: vi.fn(),
  updateProjectIndex: vi.fn(),
  getIndexingInProgressProjects: vi.fn().mockReturnValue([]),
  requestCancellation: vi.fn(),
}));

vi.mock("../../src/services/lock.js", () => ({
  getLockHolderPid: vi.fn(),
  releaseAllLocks: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("../../src/services/watcher.js", () => ({
  isWatching: vi.fn().mockReturnValue(false),
  startWatching: vi.fn().mockResolvedValue(true),
  stopAllWatchers: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("../../src/services/logger.js", () => ({
  logger: {
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    debug: vi.fn(),
  },
}));

// Mock constants — default to "managed" mode
vi.mock("../../src/constants.js", async (importOriginal) => {
  const original = await importOriginal<Record<string, unknown>>();
  return { ...original, QDRANT_MODE: "managed" };
});

// Config uses real SHA-256 logic — don't mock
// vi.mock("../../src/config.js") is NOT mocked

import { collectionName, projectIdFromPath } from "../../src/config.js";
import { isDockerAvailable, isQdrantRunning } from "../../src/services/docker.js";
import { getIndexingInProgressProjects, getPersistedIndexingStatus, indexProject, requestCancellation, updateProjectIndex } from "../../src/services/indexer.js";
import { getLockHolderPid, releaseAllLocks } from "../../src/services/lock.js";
import { logger } from "../../src/services/logger.js";
import { listCodebaseCollections } from "../../src/services/qdrant.js";
import { autoResumeIndexedProjects, awaitActiveIndexing, gracefulShutdown } from "../../src/services/startup.js";
import { isWatching, startWatching, stopAllWatchers } from "../../src/services/watcher.js";

// Typed mock helpers
const mockIsDockerAvailable = vi.mocked(isDockerAvailable);
const mockIsQdrantRunning = vi.mocked(isQdrantRunning);
const mockListCollections = vi.mocked(listCodebaseCollections);
const mockGetPersistedStatus = vi.mocked(getPersistedIndexingStatus);
const mockIndexProject = vi.mocked(indexProject);
const mockUpdateProjectIndex = vi.mocked(updateProjectIndex);
const mockGetIndexingInProgress = vi.mocked(getIndexingInProgressProjects);
const mockRequestCancellation = vi.mocked(requestCancellation);
const mockGetLockHolderPid = vi.mocked(getLockHolderPid);
const mockIsWatching = vi.mocked(isWatching);
const mockStartWatching = vi.mocked(startWatching);
const mockStopAllWatchers = vi.mocked(stopAllWatchers);
const mockReleaseAllLocks = vi.mocked(releaseAllLocks);

// A plausible project path for tests
const TEST_PROJECT = "/tmp/test-project";

beforeEach(() => {
  vi.clearAllMocks();
  // Default: Docker and Qdrant are running
  mockIsDockerAvailable.mockResolvedValue(true);
  mockIsQdrantRunning.mockResolvedValue(true);
  mockGetIndexingInProgress.mockReturnValue([]);
});

// ── autoResumeIndexedProjects ────────────────────────────────────────────

describe("autoResumeIndexedProjects", () => {
  it("skips when Docker is not available (managed mode)", async () => {
    mockIsDockerAvailable.mockResolvedValue(false);

    await autoResumeIndexedProjects(TEST_PROJECT);

    expect(mockIsDockerAvailable).toHaveBeenCalled();
    expect(mockListCollections).not.toHaveBeenCalled();
    expect(logger.info).toHaveBeenCalledWith("Auto-resume: Docker not available, skipping");
  });

  it("skips when Qdrant is not running (managed mode)", async () => {
    mockIsQdrantRunning.mockResolvedValue(false);

    await autoResumeIndexedProjects(TEST_PROJECT);

    expect(mockIsQdrantRunning).toHaveBeenCalled();
    expect(mockListCollections).not.toHaveBeenCalled();
    expect(logger.info).toHaveBeenCalledWith("Auto-resume: Qdrant not running, skipping");
  });

  it("skips when projectPath is root (/)", async () => {
    await autoResumeIndexedProjects("/");

    expect(mockListCollections).not.toHaveBeenCalled();
    expect(logger.info).toHaveBeenCalledWith(
      "Auto-resume: CWD is root/home, no specific project — skipping",
      expect.objectContaining({ projectPath: "/" }),
    );
  });

  it("skips when projectPath is HOME", async () => {
    const home = process.env.HOME ?? "/tmp";
    await autoResumeIndexedProjects(home);

    expect(mockListCollections).not.toHaveBeenCalled();
  });

  it("skips when project has no collection (not yet indexed)", async () => {
    mockListCollections.mockResolvedValue([]);

    await autoResumeIndexedProjects(TEST_PROJECT);

    expect(mockListCollections).toHaveBeenCalled();
    expect(mockGetPersistedStatus).not.toHaveBeenCalled();
    expect(logger.info).toHaveBeenCalledWith(
      "Auto-resume: current project not yet indexed, skipping",
      expect.objectContaining({ projectPath: TEST_PROJECT }),
    );
  });

  it("skips incomplete index recovery when another process holds the lock", async () => {
    const pid = projectIdFromPath(TEST_PROJECT);
    const coll = collectionName(pid);
    mockListCollections.mockResolvedValue([coll]);
    mockGetPersistedStatus.mockResolvedValue("in-progress");
    mockGetLockHolderPid.mockResolvedValue(12345);

    await autoResumeIndexedProjects(TEST_PROJECT);

    expect(mockGetLockHolderPid).toHaveBeenCalledWith(TEST_PROJECT, "index");
    expect(mockIndexProject).not.toHaveBeenCalled();
    expect(logger.info).toHaveBeenCalledWith(
      "Auto-resume: skipping — another process is still indexing this project",
      expect.objectContaining({ orphanPid: 12345 }),
    );
  });

  it("resumes incomplete index when no lock holder exists", async () => {
    const pid = projectIdFromPath(TEST_PROJECT);
    const coll = collectionName(pid);
    mockListCollections.mockResolvedValue([coll]);
    mockGetPersistedStatus.mockResolvedValue("in-progress");
    mockGetLockHolderPid.mockResolvedValue(null);

    const indexResult = { filesIndexed: 8, chunksCreated: 100, cancelled: false };
    mockIndexProject.mockResolvedValue(indexResult);

    await autoResumeIndexedProjects(TEST_PROJECT);

    expect(mockIndexProject).toHaveBeenCalledWith(TEST_PROJECT, expect.any(Function));
    expect(logger.info).toHaveBeenCalledWith(
      "Auto-resume: detected incomplete index, resuming indexing",
      expect.objectContaining({ projectPath: TEST_PROJECT }),
    );

    // Wait a tick for the .then() chain to resolve
    await vi.waitFor(() => {
      expect(logger.info).toHaveBeenCalledWith(
        "Auto-resume: incomplete index recovery completed",
        expect.objectContaining({
          filesIndexed: 8,
          chunksCreated: 100,
          cancelled: false,
        }),
      );
    });
  });

  it("starts watcher after successful incomplete index recovery", async () => {
    const pid = projectIdFromPath(TEST_PROJECT);
    const coll = collectionName(pid);
    mockListCollections.mockResolvedValue([coll]);
    mockGetPersistedStatus.mockResolvedValue("in-progress");
    mockGetLockHolderPid.mockResolvedValue(null);
    mockIsWatching.mockReturnValue(false);
    mockIndexProject.mockResolvedValue({ filesIndexed: 1, chunksCreated: 10, cancelled: false });

    await autoResumeIndexedProjects(TEST_PROJECT);

    await vi.waitFor(() => {
      expect(mockStartWatching).toHaveBeenCalledWith(TEST_PROJECT);
    });
  });

  it("does not start watcher after cancelled recovery", async () => {
    const pid = projectIdFromPath(TEST_PROJECT);
    const coll = collectionName(pid);
    mockListCollections.mockResolvedValue([coll]);
    mockGetPersistedStatus.mockResolvedValue("in-progress");
    mockGetLockHolderPid.mockResolvedValue(null);
    mockIndexProject.mockResolvedValue({ filesIndexed: 1, chunksCreated: 10, cancelled: true });

    await autoResumeIndexedProjects(TEST_PROJECT);

    // Give the .then() time to fire
    await new Promise((r) => setTimeout(r, 50));
    expect(mockStartWatching).not.toHaveBeenCalled();
  });

  it("starts watcher and runs incremental update for completed index", async () => {
    const pid = projectIdFromPath(TEST_PROJECT);
    const coll = collectionName(pid);
    mockListCollections.mockResolvedValue([coll]);
    mockGetPersistedStatus.mockResolvedValue("completed");
    mockIsWatching.mockReturnValue(false);
    mockUpdateProjectIndex.mockResolvedValue({ added: 3, updated: 1, removed: 0, chunksCreated: 40, cancelled: false });

    await autoResumeIndexedProjects(TEST_PROJECT);

    expect(mockStartWatching).toHaveBeenCalledWith(TEST_PROJECT);
    expect(mockUpdateProjectIndex).toHaveBeenCalledWith(TEST_PROJECT);

    await vi.waitFor(() => {
      expect(logger.info).toHaveBeenCalledWith(
        "Auto-resume: incremental update completed",
        expect.objectContaining({ filesChanged: 4 }),
      );
    });
  });

  it("logs 'up to date' when incremental update finds no changes", async () => {
    const pid = projectIdFromPath(TEST_PROJECT);
    const coll = collectionName(pid);
    mockListCollections.mockResolvedValue([coll]);
    mockGetPersistedStatus.mockResolvedValue("completed");
    mockIsWatching.mockReturnValue(false);
    mockUpdateProjectIndex.mockResolvedValue({ added: 0, updated: 0, removed: 0, chunksCreated: 0, cancelled: false });

    await autoResumeIndexedProjects(TEST_PROJECT);

    await vi.waitFor(() => {
      expect(logger.info).toHaveBeenCalledWith(
        "Auto-resume: index is up to date",
        expect.objectContaining({ projectPath: TEST_PROJECT }),
      );
    });
  });

  it("does not re-start watcher if already watching", async () => {
    const pid = projectIdFromPath(TEST_PROJECT);
    const coll = collectionName(pid);
    mockListCollections.mockResolvedValue([coll]);
    mockGetPersistedStatus.mockResolvedValue("completed");
    mockIsWatching.mockReturnValue(true); // already watching
    mockUpdateProjectIndex.mockResolvedValue({ added: 0, updated: 0, removed: 0, chunksCreated: 0, cancelled: false });

    await autoResumeIndexedProjects(TEST_PROJECT);

    expect(mockStartWatching).not.toHaveBeenCalled();
  });

  it("handles updateProjectIndex failure gracefully for completed index", async () => {
    const pid = projectIdFromPath(TEST_PROJECT);
    const coll = collectionName(pid);
    mockListCollections.mockResolvedValue([coll]);
    mockGetPersistedStatus.mockResolvedValue("completed");
    mockIsWatching.mockReturnValue(false);
    mockUpdateProjectIndex.mockRejectedValue(new Error("Qdrant unavailable"));

    await autoResumeIndexedProjects(TEST_PROJECT);

    await vi.waitFor(() => {
      expect(logger.warn).toHaveBeenCalledWith(
        "Auto-resume: incremental update failed (non-fatal)",
        expect.objectContaining({ error: "Qdrant unavailable" }),
      );
    });
  });

  it("handles indexProject failure gracefully for in-progress index", async () => {
    const pid = projectIdFromPath(TEST_PROJECT);
    const coll = collectionName(pid);
    mockListCollections.mockResolvedValue([coll]);
    mockGetPersistedStatus.mockResolvedValue("in-progress");
    mockGetLockHolderPid.mockResolvedValue(null);
    mockIndexProject.mockRejectedValue(new Error("Crash during resume"));

    await autoResumeIndexedProjects(TEST_PROJECT);

    await vi.waitFor(() => {
      expect(logger.warn).toHaveBeenCalledWith(
        "Auto-resume: incomplete index recovery failed (non-fatal)",
        expect.objectContaining({ error: "Crash during resume" }),
      );
    });
  });

  it("catches top-level errors and logs a warning", async () => {
    mockIsDockerAvailable.mockRejectedValue(new Error("Docker daemon gone"));

    await autoResumeIndexedProjects(TEST_PROJECT);

    expect(logger.warn).toHaveBeenCalledWith(
      "Auto-resume failed (non-fatal)",
      expect.objectContaining({ error: "Docker daemon gone" }),
    );
  });
});

// ── awaitActiveIndexing ──────────────────────────────────────────────────

describe("awaitActiveIndexing", () => {
  it("returns immediately when no indexing is in progress", async () => {
    mockGetIndexingInProgress.mockReturnValue([]);

    const start = Date.now();
    await awaitActiveIndexing(5000);
    const elapsed = Date.now() - start;

    expect(elapsed).toBeLessThan(200);
  });

  it("waits until indexing completes", async () => {
    // First call returns active, subsequent calls return empty
    let calls = 0;
    mockGetIndexingInProgress.mockImplementation(() => {
      calls++;
      return calls <= 2 ? ["/tmp/proj"] : [];
    });

    await awaitActiveIndexing(10_000);

    expect(calls).toBeGreaterThan(2);
  });

  it("times out and logs a warning when indexing persists", async () => {
    mockGetIndexingInProgress.mockReturnValue(["/tmp/stuck-project"]);

    await awaitActiveIndexing(1000); // 1 second timeout

    expect(logger.warn).toHaveBeenCalledWith(
      expect.stringContaining("Forcing shutdown"),
      expect.objectContaining({ projects: ["/tmp/stuck-project"] }),
    );
  });

  it("logs active projects at the start", async () => {
    mockGetIndexingInProgress
      .mockReturnValueOnce(["/proj-a", "/proj-b"]) // first call — reported
      .mockReturnValue([]); // subsequent — done

    await awaitActiveIndexing(5000);

    expect(logger.info).toHaveBeenCalledWith(
      "Waiting for active indexing to complete before shutdown",
      expect.objectContaining({ projects: ["/proj-a", "/proj-b"] }),
    );
  });
});

// ── gracefulShutdown ─────────────────────────────────────────────────────

describe("gracefulShutdown", () => {
  it("requests cancellation for all in-progress projects", async () => {
    mockGetIndexingInProgress
      .mockReturnValueOnce(["/proj-a", "/proj-b"]) // for cancellation loop
      .mockReturnValue([]); // for awaitActiveIndexing

    await gracefulShutdown("SIGTERM");

    expect(mockRequestCancellation).toHaveBeenCalledWith("/proj-a");
    expect(mockRequestCancellation).toHaveBeenCalledWith("/proj-b");
  });

  it("stops all watchers and releases all locks", async () => {
    await gracefulShutdown("SIGINT");

    expect(mockStopAllWatchers).toHaveBeenCalled();
    expect(mockReleaseAllLocks).toHaveBeenCalled();
  });

  it("calls the closeServer callback if provided", async () => {
    const closeFn = vi.fn().mockResolvedValue(undefined);

    await gracefulShutdown("SIGTERM", closeFn);

    expect(closeFn).toHaveBeenCalledOnce();
  });

  it("works without a closeServer callback", async () => {
    // Should not throw
    await gracefulShutdown("stdin EOF");
    expect(logger.info).toHaveBeenCalledWith(expect.stringContaining("stdin EOF"));
  });

  it("logs the signal name", async () => {
    await gracefulShutdown("SIGTERM");

    expect(logger.info).toHaveBeenCalledWith("Received SIGTERM, shutting down gracefully...");
  });

  it("logs completion at the end", async () => {
    await gracefulShutdown("SIGTERM");

    expect(logger.info).toHaveBeenCalledWith("Graceful shutdown complete");
  });
});

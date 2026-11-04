"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import "./workspace.css";

type Source = {
  id: string;
  original_filename: string;
  media_format: string;
  size_bytes: number;
  duration_seconds: number;
  created_at: string;
  expires_at: string;
};

type Project = {
  id: string;
  team_id: string;
  name: string;
  youtube_url: string | null;
  youtube_video_id: string | null;
  youtube_rights_confirmed_at: string | null;
  created_at: string;
  sources: Source[];
  transcription_jobs: TranscriptionJob[];
  candidate_runs: CandidateRun[];
};

type TranscriptionJob = {
  id: string;
  source_id: string;
  status: string;
  stage: string;
  progress_percent: number | null;
  attempt_count: number;
  max_attempts: number;
  model_id: string;
  requested_language: string | null;
  detected_language: string | null;
  language_probability: number | null;
  failure_message: string | null;
  retryable: boolean;
  created_at: string;
  updated_at: string;
};

type TranscriptSegment = {
  id: string;
  ordinal: number;
  start_ms: number;
  end_ms: number;
  text: string;
};

type HighlightCandidate = {
  id: string;
  ordinal: number;
  start_ms: number;
  end_ms: number;
  title: string;
  summary: string | null;
  transcript_excerpt: string;
  signals: string[];
  status: string;
  created_at: string;
  updated_at: string;
  render_jobs: RenderJob[];
  caption_edits: Record<string, string>;
  editor_settings: EditorSettings;
};

type EditorSettings = { aspect_ratio: "9:16" | "1:1" | "16:9"; crop_mode: "fit_blur" | "fill_crop"; focus_x: number; focus_y: number };

type RenderJob = {
  id: string; candidate_id: string; status: string; stage: string; progress_percent: number | null;
  caption_mode: string; output_size_bytes: number | null; duration_ms: number | null;
  failure_message: string | null; retryable: boolean; download_url: string | null; captions_url: string | null;
};

type CandidateRun = {
  id: string;
  transcription_job_id: string;
  min_duration_seconds: number;
  max_duration_seconds: number;
  candidate_limit: number;
  total_candidates: number;
  sampled_evenly: boolean;
  created_at: string;
  candidates: HighlightCandidate[];
};

type IntakeConfig = {
  accepted_formats: string[];
  max_upload_bytes: number;
  max_media_storage_bytes: number;
  max_video_duration_seconds: number;
  source_retention_days: number;
  youtube_processing: boolean;
  access_scope: string;
};

const API = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(/\/+$/, "");
let csrfToken = "";

function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const method = (init.method || "GET").toUpperCase();
  if (!["GET", "HEAD", "OPTIONS"].includes(method) && csrfToken) headers.set("X-CSRF-Token", csrfToken);
  return fetch(input, { ...init, credentials: "include", headers });
}

type Account = { id: string; email: string };
type TeamAccount = { id: string; name: string; role: "owner" | "editor" | "reviewer" };
type TeamMember = { email: string; role: string; membership_id: string };

function formatBytes(bytes: number): string {
  if (bytes >= 1024 ** 3) {
    const gigabytes = bytes / 1024 ** 3;
    return `${Number.isInteger(gigabytes) ? gigabytes.toFixed(0) : gigabytes.toFixed(1)} GB`;
  }
  if (bytes >= 1024 ** 2) {
    const megabytes = bytes / 1024 ** 2;
    return `${Number.isInteger(megabytes) ? megabytes.toFixed(0) : megabytes.toFixed(1)} MB`;
  }
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}

function formatDuration(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds % 60;
  return hours ? `${hours}h ${minutes}m` : `${minutes}m ${remainder}s`;
}

function formatTimestamp(milliseconds: number): string {
  const totalSeconds = Math.floor(milliseconds / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return hours
    ? `${hours}:${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`
    : `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

const ACTIVE_JOB_STATUSES = new Set(["queued", "validating", "extracting", "transcribing", "saving"]);
const ACTIVE_RENDER_STATUSES = new Set(["queued", "validating", "rendering"]);
const JOB_STAGE_LABELS: Record<string, string> = {
  queued: "Waiting for the transcription worker",
  validating: "Checking source availability",
  extracting: "Extracting audio",
  transcribing: "Transcribing speech",
  saving: "Saving timestamped transcript",
  complete: "Transcript ready",
  failed: "Transcription failed",
  cancelled: "Transcription cancelled",
};

async function responseError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    const detail = body.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object") return JSON.stringify(detail);
  } catch {
    // Use the generic message when the server did not return JSON.
  }
  return `Request failed (${response.status}). Check that the API is running.`;
}

function drawEditorPreview(video: HTMLVideoElement, canvas: HTMLCanvasElement, settings: EditorSettings) {
  if (!video.videoWidth || !video.videoHeight) return;
  const ratio = settings.aspect_ratio === "9:16" ? 9 / 16 : settings.aspect_ratio === "1:1" ? 1 : 16 / 9;
  const width = 480, height = Math.round(width / ratio);
  if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
  const context = canvas.getContext("2d");
  if (!context) return;
  const sourceRatio = video.videoWidth / video.videoHeight;
  const crop = () => {
    if (sourceRatio > ratio) {
      const cropWidth = video.videoHeight * ratio;
      return [Math.max(0, (video.videoWidth - cropWidth) * settings.focus_x), 0, cropWidth, video.videoHeight] as const;
    }
    const cropHeight = video.videoWidth / ratio;
    return [0, Math.max(0, (video.videoHeight - cropHeight) * settings.focus_y), video.videoWidth, cropHeight] as const;
  };
  context.clearRect(0, 0, width, height);
  if (settings.crop_mode === "fill_crop") {
    const [sx, sy, sw, sh] = crop();
    context.drawImage(video, sx, sy, sw, sh, 0, 0, width, height);
    return;
  }
  const [sx, sy, sw, sh] = crop();
  context.save(); context.filter = "blur(18px)";
  context.drawImage(video, sx, sy, sw, sh, -16, -16, width + 32, height + 32);
  context.restore();
  const scale = Math.min(width / video.videoWidth, height / video.videoHeight);
  const drawWidth = video.videoWidth * scale, drawHeight = video.videoHeight * scale;
  context.drawImage(video, (width - drawWidth) / 2, (height - drawHeight) / 2, drawWidth, drawHeight);
}

function CreatorEditor({ projectId, transcriptionJobId, sourceDuration, candidate, onSaved, readOnly }: {
  projectId: string; transcriptionJobId: string; sourceDuration: number;
  candidate: HighlightCandidate; onSaved: () => void; readOnly: boolean;
}) {
  const defaultSettings: EditorSettings = { aspect_ratio: "9:16", crop_mode: "fit_blur", focus_x: 0.5, focus_y: 0.5 };
  const [title, setTitle] = useState(candidate.title);
  const [start, setStart] = useState(candidate.start_ms / 1000);
  const [end, setEnd] = useState(candidate.end_ms / 1000);
  const [captionEdits, setCaptionEdits] = useState<Record<string, string>>(candidate.caption_edits ?? {});
  const [settings, setSettings] = useState<EditorSettings>({ ...defaultSettings, ...(candidate.editor_settings ?? {}) });
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [saveState, setSaveState] = useState("Saved");
  const [saveError, setSaveError] = useState("");
  const [currentMs, setCurrentMs] = useState(candidate.start_ms);
  const [playing, setPlaying] = useState(false);
  const sourceVideo = useRef<HTMLVideoElement | null>(null);
  const previewCanvas = useRef<HTMLCanvasElement | null>(null);
  const savedPayload = useRef<string>(JSON.stringify({
    title: candidate.title, start_ms: candidate.start_ms, end_ms: candidate.end_ms,
    caption_edits: candidate.caption_edits ?? {}, editor_settings: { ...defaultSettings, ...(candidate.editor_settings ?? {}) },
  }));

  useEffect(() => {
    const controller = new AbortController();
    apiFetch(`${API}/api/transcription-jobs/${transcriptionJobId}/transcript`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => { if (!response.ok) throw new Error(await responseError(response)); return response.json(); })
      .then((data: TranscriptSegment[]) => setSegments(data))
      .catch((reason) => { if (!(reason instanceof DOMException && reason.name === "AbortError")) setSaveError("Transcript captions could not be loaded."); });
    return () => controller.abort();
  }, [transcriptionJobId]);

  useEffect(() => {
    setTitle(candidate.title); setStart(candidate.start_ms / 1000); setEnd(candidate.end_ms / 1000);
    setCaptionEdits(candidate.caption_edits ?? {});
    setSettings({ ...defaultSettings, ...(candidate.editor_settings ?? {}) });
    savedPayload.current = JSON.stringify({ title: candidate.title, start_ms: candidate.start_ms, end_ms: candidate.end_ms,
      caption_edits: candidate.caption_edits ?? {}, editor_settings: { ...defaultSettings, ...(candidate.editor_settings ?? {}) } });
  }, [candidate.id, candidate.updated_at]);

  useEffect(() => {
    const startMs = Math.round(start * 1000), endMs = Math.round(end * 1000);
    if (readOnly || !title.trim() || start < 0 || end <= start || end > sourceDuration) return;
    const body = { title, start_ms: startMs, end_ms: endMs, caption_edits: captionEdits, editor_settings: settings };
    const serialized = JSON.stringify(body);
    if (serialized === savedPayload.current) return;
    setSaveState("Unsaved changes");
    const timer = window.setTimeout(async () => {
      setSaveState("Saving…"); setSaveError("");
      try {
        const response = await apiFetch(`${API}/api/candidates/${candidate.id}`, {
          method: "PATCH", headers: { "Content-Type": "application/json" }, body: serialized,
        });
        if (!response.ok) throw new Error(await responseError(response));
        savedPayload.current = serialized; setSaveState("Saved"); onSaved();
      } catch (reason) {
        setSaveState("Not saved"); setSaveError(reason instanceof Error ? reason.message : "Editor changes could not be saved.");
      }
    }, 700);
    return () => window.clearTimeout(timer);
  }, [title, start, end, captionEdits, settings, sourceDuration, candidate.id, onSaved, readOnly]);

  useEffect(() => {
    const video = sourceVideo.current, canvas = previewCanvas.current;
    if (!video || !canvas) return;
    const draw = () => drawEditorPreview(video, canvas, settings);
    draw();
    if (!playing) return;
    let frame = 0;
    const animate = () => { draw(); frame = requestAnimationFrame(animate); };
    frame = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frame);
  }, [settings, playing]);

  useEffect(() => {
    const video = sourceVideo.current;
    if (video && video.currentTime < start) video.currentTime = start;
  }, [start]);

  function setVideoTime(milliseconds: number) {
    const video = sourceVideo.current;
    if (video) { video.currentTime = milliseconds / 1000; void video.play(); }
  }

  const visibleSegments = segments.filter((segment) => segment.start_ms < end * 1000 && segment.end_ms > start * 1000);
  const frameRatio = settings.aspect_ratio === "9:16" ? "9 / 16" : settings.aspect_ratio === "1:1" ? "1 / 1" : "16 / 9";
  const validRange = start >= 0 && end > start && end <= sourceDuration;
  return <section className="creator-editor" aria-label={`Editor for ${candidate.title}`}>
    <div className="editor-heading"><div><p className="panel-kicker">MILESTONE 05 · CREATOR EDITOR</p><strong>Make the draft yours</strong></div><span role="status">{saveState}</span></div>
    <div className="editor-preview" style={{ aspectRatio: frameRatio }}><canvas ref={previewCanvas} aria-label={`${settings.aspect_ratio} composition preview for ${candidate.title}`} role="img" /><video ref={sourceVideo} className="editor-source-video" crossOrigin="use-credentials" preload="metadata" muted playsInline src={`${API}/api/projects/${projectId}/source/preview`}
      onLoadedMetadata={(event) => { event.currentTarget.currentTime = start; }} onLoadedData={(event) => { if (previewCanvas.current) drawEditorPreview(event.currentTarget, previewCanvas.current, settings); }}
      onSeeked={(event) => { if (previewCanvas.current) drawEditorPreview(event.currentTarget, previewCanvas.current, settings); }}
      onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)}
      onTimeUpdate={(event) => { const ms = Math.round(event.currentTarget.currentTime * 1000); setCurrentMs(ms); if (previewCanvas.current) drawEditorPreview(event.currentTarget, previewCanvas.current, settings); if (ms >= end * 1000) { event.currentTarget.pause(); event.currentTarget.currentTime = end; } }} />
    </div>
    <div className="editor-transport"><button type="button" onClick={() => { const video = sourceVideo.current; if (!video) return; if (video.paused) { if (video.currentTime < start || video.currentTime >= end) video.currentTime = start; void video.play(); } else video.pause(); }}>{playing ? "Pause preview" : "Play clip"}</button><label>Preview playhead<input aria-label="Preview playhead" type="range" min={start} max={Math.max(start, end)} step="0.05" value={Math.min(end, Math.max(start, currentMs / 1000))} onChange={(event) => { const video = sourceVideo.current; if (video) video.currentTime = Number(event.target.value); }} /></label></div>
    <p className="editor-playhead">Preview time {formatTimestamp(currentMs)} · transcript rows seek the preview to their start</p>
    <div className="editor-controls">
      <label>Clip title<input aria-label="Clip title" maxLength={120} value={title} disabled={readOnly} onChange={(event) => setTitle(event.target.value)} /></label>
      <label>In point (seconds)<input aria-label="Clip in point seconds" type="number" min="0" max={sourceDuration} step="0.001" value={start} disabled={readOnly} onChange={(event) => setStart(Number(event.target.value))} /></label>
      <label>Out point (seconds)<input aria-label="Clip out point seconds" type="number" min="0.001" max={sourceDuration} step="0.001" value={end} disabled={readOnly} onChange={(event) => setEnd(Number(event.target.value))} /></label>
      <label>Timeline in<input aria-label="Timeline in point" type="range" min="0" max={Math.max(0, end - 0.1)} step="0.1" value={Math.min(start, Math.max(0, end - 0.1))} disabled={readOnly} onChange={(event) => setStart(Number(event.target.value))} /></label>
      <label>Timeline out<input aria-label="Timeline out point" type="range" min={Math.min(sourceDuration, start + 0.1)} max={sourceDuration} step="0.1" value={Math.min(sourceDuration, Math.max(start + 0.1, end))} disabled={readOnly} onChange={(event) => setEnd(Number(event.target.value))} /></label>
      <label>Local frame preset<select value={settings.aspect_ratio} disabled={readOnly} onChange={(event) => setSettings((value) => ({ ...value, aspect_ratio: event.target.value as EditorSettings["aspect_ratio"] }))}><option value="9:16">Portrait · 9:16 · 720 × 1280</option><option value="1:1">Square · 1:1 · 720 × 720</option><option value="16:9">Landscape · 16:9 · 1280 × 720</option></select></label>
      <label>Frame composition<select value={settings.crop_mode} disabled={readOnly} onChange={(event) => setSettings((value) => ({ ...value, crop_mode: event.target.value as EditorSettings["crop_mode"] }))}><option value="fit_blur">Fit full frame over blur</option><option value="fill_crop">Fill frame and crop</option></select></label>
      {settings.crop_mode === "fill_crop" && <>
        <label>Focus left ↔ right<input type="range" min="0" max="1" step="0.01" value={settings.focus_x} disabled={readOnly} onChange={(event) => setSettings((value) => ({ ...value, focus_x: Number(event.target.value) }))} /></label>
        <label>Focus top ↕ bottom<input type="range" min="0" max="1" step="0.01" value={settings.focus_y} disabled={readOnly} onChange={(event) => setSettings((value) => ({ ...value, focus_y: Number(event.target.value) }))} /></label>
      </>}
    </div>
    {!validRange && <p className="job-failure" role="alert">Set an in and out point inside the source. Autosave resumes when the range is valid.</p>}
    <div className="caption-editor"><p className="panel-kicker">CAPTION CORRECTIONS · AUTOSAVED</p>
      {visibleSegments.map((segment) => <div className={`caption-row ${currentMs >= segment.start_ms && currentMs < segment.end_ms ? "caption-row-active" : ""}`} key={segment.id}>
        <button type="button" onClick={() => setVideoTime(segment.start_ms)} aria-label={`Seek preview to ${formatTimestamp(segment.start_ms)}`}><time>{formatTimestamp(segment.start_ms)}</time></button>
        <textarea rows={2} disabled={readOnly} aria-label={`Caption at ${formatTimestamp(segment.start_ms)}`} value={captionEdits[segment.id] ?? segment.text}
          onChange={(event) => setCaptionEdits((value) => ({ ...value, [segment.id]: event.target.value }))} />
      </div>)}
      {!visibleSegments.length && <p>Transcript segments will appear here after loading.</p>}
    </div>
    {saveError && <p role="alert" className="job-failure">{saveError}</p>}
  </section>;
}

export default function WorkspacePage() {
  const [account, setAccount] = useState<Account | null>(null);
  const [teams, setTeams] = useState<TeamAccount[]>([]);
  const [selectedTeamId, setSelectedTeamId] = useState("");
  const [authLoading, setAuthLoading] = useState(true);
  const [setupRequired, setSetupRequired] = useState(false);
  const [authMode, setAuthMode] = useState<"login" | "register" | "accept">("login");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [inviteToken, setInviteToken] = useState("");
  const [authError, setAuthError] = useState("");
  const [authBusy, setAuthBusy] = useState(false);
  const [teamMembers, setTeamMembers] = useState<Record<string, TeamMember[]>>({});
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"editor" | "reviewer">("reviewer");
  const [inviteUrl, setInviteUrl] = useState("");
  const [inviteError, setInviteError] = useState("");
  const [passwordChangeOpen, setPasswordChangeOpen] = useState(false);
  const [newTeamName, setNewTeamName] = useState("");
  const [teamCreateError, setTeamCreateError] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [config, setConfig] = useState<IntakeConfig | null>(null);
  const [projectName, setProjectName] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [expandedTranscriptId, setExpandedTranscriptId] = useState<string | null>(null);
  const [transcripts, setTranscripts] = useState<Record<string, TranscriptSegment[]>>({});

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const invite = new URLSearchParams(window.location.search).get("invite") || "";
        setInviteToken(invite);
        const statusResponse = await apiFetch(`${API}/api/auth/status`, { cache: "no-store" });
        if (!statusResponse.ok) throw new Error(await responseError(statusResponse));
        const statusData = await statusResponse.json();
        if (!active) return;
        setSetupRequired(statusData.needs_setup);
        setAuthMode(statusData.needs_setup ? "register" : invite ? "accept" : "login");
        if (!statusData.needs_setup) {
          const response = await apiFetch(`${API}/api/auth/me`, { cache: "no-store" });
          if (response.ok) {
            const data = await response.json();
            if (active) { csrfToken = data.csrf_token; setAccount(data.user); setTeams(data.teams); setSelectedTeamId(data.teams.find((team: TeamAccount) => team.role !== "reviewer")?.id ?? ""); }
          }
        }
      } catch (reason) {
        if (active) setAuthError(reason instanceof Error ? reason.message : "The account service could not be reached.");
      } finally { if (active) setAuthLoading(false); }
    })();
    return () => { active = false; };
  }, []);

  const loadWorkspace = useCallback(async () => {
    try {
      const [projectResponse, configResponse] = await Promise.all([
        apiFetch(`${API}/api/projects`, { cache: "no-store" }),
        apiFetch(`${API}/api/intake/config`, { cache: "no-store" }),
      ]);
      if (!projectResponse.ok) throw new Error(await responseError(projectResponse));
      if (!configResponse.ok) throw new Error(await responseError(configResponse));
      setProjects(await projectResponse.json());
      setConfig(await configResponse.json());
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The workspace could not be loaded.");
    }
  }, []);

  useEffect(() => {
    if (account) void loadWorkspace();
  }, [loadWorkspace, account]);

  useEffect(() => {
    if (!account) return;
    const hasActiveJob = projects.some((project) =>
      project.transcription_jobs.some((job) => ACTIVE_JOB_STATUSES.has(job.status)) ||
      project.candidate_runs.some((run) => run.candidates.some((candidate) => candidate.render_jobs?.some((render) => ACTIVE_RENDER_STATUSES.has(render.status)))),
    );
    if (!hasActiveJob) return;
    const timer = window.setTimeout(() => void loadWorkspace(), 3500);
    return () => window.clearTimeout(timer);
  }, [projects, loadWorkspace, account]);

  useEffect(() => {
    if (!account || teams.length === 0) return;
    let active = true;
    void Promise.all(teams.map(async (team) => {
      const response = await apiFetch(`${API}/api/teams/${team.id}/members`, { cache: "no-store" });
      if (!response.ok) return [team.id, []] as const;
      return [team.id, await response.json() as TeamMember[]] as const;
    })).then((rows) => { if (active) setTeamMembers(Object.fromEntries(rows)); });
    return () => { active = false; };
  }, [account, teams]);

  async function startTranscription(project: Project) {
    setBusyId(project.id);
    setError("");
    setMessage("");
    try {
      const response = await apiFetch(`${API}/api/projects/${project.id}/transcription-jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!response.ok) throw new Error(await responseError(response));
      setMessage("Transcription queued. You can keep this page open to follow its progress.");
      await loadWorkspace();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The transcription job could not be started.");
    } finally {
      setBusyId(null);
    }
  }

  async function retryTranscription(project: Project, job: TranscriptionJob) {
    setBusyId(project.id);
    setError("");
    setMessage("");
    try {
      const response = await apiFetch(`${API}/api/transcription-jobs/${job.id}/retry`, { method: "POST" });
      if (!response.ok) throw new Error(await responseError(response));
      setMessage("Transcription retry queued.");
      await loadWorkspace();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The transcription could not be retried.");
    } finally {
      setBusyId(null);
    }
  }

  async function cancelTranscription(project: Project, job: TranscriptionJob) {
    if (!window.confirm("Cancel this transcription? If audio extraction or speech recognition is already running, it will finish its current operation before discarding the result.")) return;
    setBusyId(project.id);
    setError("");
    setMessage("");
    try {
      const response = await apiFetch(`${API}/api/transcription-jobs/${job.id}/cancel`, { method: "POST" });
      if (!response.ok) throw new Error(await responseError(response));
      setMessage("Transcription cancelled. Any in-progress media or model operation will discard its result when it finishes.");
      await loadWorkspace();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The transcription could not be cancelled.");
    } finally {
      setBusyId(null);
    }
  }

  async function toggleTranscript(job: TranscriptionJob) {
    if (expandedTranscriptId === job.id) {
      setExpandedTranscriptId(null);
      return;
    }
    setError("");
    setExpandedTranscriptId(job.id);
    if (transcripts[job.id]) return;
    try {
      const response = await apiFetch(`${API}/api/transcription-jobs/${job.id}/transcript`, { cache: "no-store" });
      if (!response.ok) throw new Error(await responseError(response));
      const segments: TranscriptSegment[] = await response.json();
      setTranscripts((current) => ({ ...current, [job.id]: segments }));
    } catch (reason) {
      setExpandedTranscriptId(null);
      setError(reason instanceof Error ? reason.message : "The transcript could not be loaded.");
    }
  }

  async function createCandidateRun(event: FormEvent<HTMLFormElement>, project: Project, job: TranscriptionJob) {
    event.preventDefault();
    const form = event.currentTarget;
    const minDuration = Number((form.elements.namedItem("min-duration") as HTMLInputElement).value);
    const maxDuration = Number((form.elements.namedItem("max-duration") as HTMLInputElement).value);
    const candidateLimit = Number((form.elements.namedItem("candidate-limit") as HTMLInputElement).value);
    if (minDuration > maxDuration) {
      setError("Minimum duration must not exceed maximum duration.");
      return;
    }
    setBusyId(project.id);
    setError("");
    setMessage("");
    try {
      const response = await apiFetch(`${API}/api/transcription-jobs/${job.id}/candidate-runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          min_duration_seconds: minDuration,
          max_duration_seconds: maxDuration,
          candidate_limit: candidateLimit,
        }),
      });
      if (!response.ok) throw new Error(await responseError(response));
      const run: CandidateRun = await response.json();
      setMessage(`Created ${run.candidates.length} transcript-aligned candidate windows. They are ordered for source coverage, not ranked by quality.`);
      await loadWorkspace();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Candidate windows could not be created.");
    } finally {
      setBusyId(null);
    }
  }

  async function updateCandidateStatus(project: Project, candidate: HighlightCandidate, status: "selected" | "rejected") {
    setBusyId(project.id);
    setError("");
    setMessage("");
    try {
      const response = await apiFetch(`${API}/api/candidates/${candidate.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      if (!response.ok) throw new Error(await responseError(response));
      setMessage(status === "selected" ? "Candidate marked for review." : "Candidate rejected.");
      await loadWorkspace();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Candidate review could not be saved.");
    } finally {
      setBusyId(null);
    }
  }

  async function renderCandidate(project: Project, candidate: HighlightCandidate) {
    setBusyId(project.id); setError(""); setMessage("");
    try {
      const response = await apiFetch(`${API}/api/candidates/${candidate.id}/renders`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ caption_mode: "burn_in" }),
      });
      if (!response.ok) throw new Error(await responseError(response));
      setMessage("Local portrait render queued. Keep this workspace open to follow progress.");
      await loadWorkspace();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The clip render could not be queued."); }
    finally { setBusyId(null); }
  }

  async function cancelRender(project: Project, render: RenderJob) {
    setBusyId(project.id);
    try {
      const response = await apiFetch(`${API}/api/render-jobs/${render.id}/cancel`, { method: "POST" });
      if (!response.ok) throw new Error(await responseError(response));
      await loadWorkspace();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The render could not be cancelled."); }
    finally { setBusyId(null); }
  }

  async function retryRender(project: Project, render: RenderJob) {
    setBusyId(project.id);
    try {
      const response = await apiFetch(`${API}/api/render-jobs/${render.id}/retry`, { method: "POST" });
      if (!response.ok) throw new Error(await responseError(response));
      await loadWorkspace();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The render could not be retried."); }
    finally { setBusyId(null); }
  }

  async function createProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusyId("create");
    setError("");
    setMessage("");
    try {
      const response = await apiFetch(`${API}/api/projects`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: projectName.trim(), team_id: selectedTeamId || null }),
      });
      if (!response.ok) throw new Error(await responseError(response));
      setProjectName("");
      setMessage("Project created. Add a permission-cleared video when you’re ready.");
      await loadWorkspace();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The project could not be created.");
    } finally {
      setBusyId(null);
    }
  }

  async function uploadSource(event: FormEvent<HTMLFormElement>, project: Project) {
    event.preventDefault();
    const form = event.currentTarget;
    const fileInput = form.elements.namedItem("video") as HTMLInputElement | null;
    const rightsInput = form.elements.namedItem("rights_confirmed") as HTMLInputElement | null;
    const file = fileInput?.files?.[0];
    if (!file || !rightsInput?.checked) return;
    if (config && file.size > config.max_upload_bytes) {
      setError(`Choose a video smaller than ${formatBytes(config.max_upload_bytes)}.`);
      return;
    }
    if (!/\.(mp4|mov)$/i.test(file.name)) {
      setError("Choose an MP4 or MOV video file.");
      return;
    }

    setBusyId(project.id);
    setError("");
    setMessage("");
    const body = new FormData();
    body.append("file", file);
    body.append("rights_confirmed", "true");
    try {
      const response = await apiFetch(`${API}/api/projects/${project.id}/source`, {
        method: "POST",
        body,
      });
      if (!response.ok) throw new Error(await responseError(response));
      setMessage(`“${file.name}” was added. It will be removed automatically after ${config?.source_retention_days ?? 7} days.`);
      form.reset();
      await loadWorkspace();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The video could not be uploaded.");
    } finally {
      setBusyId(null);
    }
  }

  async function saveYouTubeReference(event: FormEvent<HTMLFormElement>, project: Project) {
    event.preventDefault();
    const form = event.currentTarget;
    const url = (form.elements.namedItem("youtube-url") as HTMLInputElement).value.trim();
    const rightsConfirmed = (form.elements.namedItem("youtube-rights") as HTMLInputElement).checked;
    if (!rightsConfirmed) return;
    setBusyId(project.id);
    setError("");
    setMessage("");
    try {
      const response = await apiFetch(`${API}/api/projects/${project.id}/youtube-reference`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, rights_confirmed: rightsConfirmed }),
      });
      if (!response.ok) throw new Error(await responseError(response));
      setMessage("YouTube link saved as a reference. To transcribe or make clips, upload a video file you’re authorized to process.");
      form.reset();
      await loadWorkspace();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The YouTube link could not be saved.");
    } finally {
      setBusyId(null);
    }
  }

  async function removeYouTubeReference(project: Project) {
    setBusyId(project.id);
    setError("");
    setMessage("");
    try {
      const response = await apiFetch(`${API}/api/projects/${project.id}/youtube-reference`, { method: "DELETE" });
      if (!response.ok) throw new Error(await responseError(response));
      setMessage("YouTube reference removed.");
      await loadWorkspace();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The YouTube reference could not be removed.");
    } finally {
      setBusyId(null);
    }
  }

  async function removeSource(project: Project) {
    if (!window.confirm("Delete this source video permanently? You will need to upload it again to restore it.")) return;
    setBusyId(project.id);
    setError("");
    setMessage("");
    try {
      const response = await apiFetch(`${API}/api/projects/${project.id}/source`, { method: "DELETE" });
      if (!response.ok) throw new Error(await responseError(response));
      setMessage("Source video deleted.");
      await loadWorkspace();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The source could not be deleted.");
    } finally {
      setBusyId(null);
    }
  }

  async function removeProject(project: Project) {
    if (!window.confirm(`Delete “${project.name}” and its source video? This removes local files permanently.`)) return;
    setBusyId(project.id);
    setError("");
    setMessage("");
    try {
      const response = await apiFetch(`${API}/api/projects/${project.id}`, { method: "DELETE" });
      if (!response.ok) throw new Error(await responseError(response));
      setMessage("Project and its local source files deleted.");
      await loadWorkspace();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The project could not be deleted.");
    } finally {
      setBusyId(null);
    }
  }

  async function submitAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setAuthBusy(true); setAuthError("");
    const endpoint = authMode === "register" ? "register" : authMode === "accept" ? "invitations/accept" : "login";
    const body = authMode === "accept" ? { email: authEmail, password: authPassword, token: inviteToken } : { email: authEmail, password: authPassword };
    try {
      const response = await apiFetch(`${API}/api/auth/${endpoint}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!response.ok) throw new Error(await responseError(response));
      const data = await response.json(); csrfToken = data.csrf_token; setAccount(data.user); setTeams(data.teams); setSelectedTeamId(data.teams.find((team: TeamAccount) => team.role !== "reviewer")?.id ?? "");
      setAuthPassword(""); setInviteToken(""); window.history.replaceState({}, "", "/workspace");
    } catch (reason) { setAuthError(reason instanceof Error ? reason.message : "Sign-in could not be completed."); }
    finally { setAuthBusy(false); }
  }

  async function signOut() {
    try { await apiFetch(`${API}/api/auth/logout`, { method: "POST" }); } finally {
      csrfToken = ""; setAccount(null); setTeams([]); setProjects([]); setTeamMembers({});
      setAuthMode("login"); setAuthPassword("");
    }
  }

  async function createInvitation(event: FormEvent<HTMLFormElement>, team: TeamAccount) {
    event.preventDefault(); setInviteError(""); setInviteUrl("");
    try {
      const response = await apiFetch(`${API}/api/teams/${team.id}/invitations`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: inviteEmail, role: inviteRole }),
      });
      if (!response.ok) throw new Error(await responseError(response));
      const result = await response.json(); setInviteUrl(result.invite_url); setInviteEmail("");
    } catch (reason) { setInviteError(reason instanceof Error ? reason.message : "The invitation could not be created."); }
  }

  async function createTeam(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setTeamCreateError("");
    try {
      const response = await apiFetch(`${API}/api/teams`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: newTeamName }) });
      if (!response.ok) throw new Error(await responseError(response));
      const team: TeamAccount = await response.json(); setTeams((value) => [...value, team]); setSelectedTeamId(team.id); setNewTeamName("");
    } catch (reason) { setTeamCreateError(reason instanceof Error ? reason.message : "The workspace could not be created."); }
  }

  async function removeMember(team: TeamAccount, member: TeamMember) {
    if (!window.confirm(`Remove ${member.email} from ${team.name}?`)) return;
    try {
      const response = await apiFetch(`${API}/api/teams/${team.id}/members/${member.membership_id}`, { method: "DELETE" });
      if (!response.ok) throw new Error(await responseError(response));
      const next = await apiFetch(`${API}/api/teams/${team.id}/members`, { cache: "no-store" });
      if (next.ok) { const members = await next.json(); setTeamMembers((value) => ({ ...value, [team.id]: members })); }
    } catch (reason) { setInviteError(reason instanceof Error ? reason.message : "The member could not be removed."); }
  }

  async function changePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = event.currentTarget;
    const current = (form.elements.namedItem("current-password") as HTMLInputElement).value;
    const next = (form.elements.namedItem("new-password") as HTMLInputElement).value;
    try {
      const response = await apiFetch(`${API}/api/auth/password`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ current_password: current, new_password: next }) });
      if (!response.ok) throw new Error(await responseError(response));
      const data = await response.json(); csrfToken = data.csrf_token; form.reset(); setMessage("Password updated. Other sign-in sessions were closed."); setPasswordChangeOpen(false);
    } catch (reason) { setInviteError(reason instanceof Error ? reason.message : "The password could not be changed."); }
  }

  if (authLoading) return <main className="workspace-page"><p role="status">Loading your workspace…</p></main>;
  if (!account) return <main className="workspace-page auth-page">
    <header className="workspace-header"><Link className="workspace-wordmark" href="/">CLIPFORGE <span>AI</span></Link><Link className="workspace-back" href="/">Back to the story ↗</Link></header>
    <section className="auth-card"><p className="workspace-eyebrow"><span /> PRIVATE WORKSPACE</p>
      <h1>{authMode === "register" ? "Set up your" : authMode === "accept" ? "Join the" : "Welcome"}<br /><em>{authMode === "accept" ? "team." : "workspace."}</em></h1>
      <p>{authMode === "register" ? "Create the first local owner account. New accounts can join only through a workspace invitation." : authMode === "accept" ? "Use the invited email and either create its password or confirm your existing password." : "Sign in to view projects in your workspaces."}</p>
      <form onSubmit={(event) => void submitAuth(event)}>
        <label>Email<input type="email" autoComplete="email" required maxLength={320} value={authEmail} onChange={(event) => setAuthEmail(event.target.value)} /></label>
        <label>Password<input type="password" autoComplete={authMode === "login" ? "current-password" : "new-password"} minLength={12} maxLength={128} required value={authPassword} onChange={(event) => setAuthPassword(event.target.value)} /></label>
        <button type="submit" disabled={authBusy}>{authBusy ? "Please wait…" : authMode === "register" ? "Create owner account" : authMode === "accept" ? "Accept invitation" : "Sign in"}<span aria-hidden="true">↗</span></button>
      </form>
      {authError && <p className="workspace-error" role="alert">{authError}</p>}
      {setupRequired && authMode !== "register" && <button className="auth-switch" type="button" onClick={() => setAuthMode("register")}>Set up the first owner account</button>}
      {!setupRequired && authMode === "login" && inviteToken && <button className="auth-switch" type="button" onClick={() => setAuthMode("accept")}>Accept workspace invitation</button>}
      {authMode === "accept" && <button className="auth-switch" type="button" onClick={() => { setInviteToken(""); setAuthMode("login"); }}>Return to sign in</button>}
      <p className="auth-local-note">Local development account service. Configure HTTPS cookies before any non-local deployment.</p>
    </section>
  </main>;

  return (
    <main className="workspace-page">
      <a className="workspace-skip" href="#projects-heading">Skip to projects</a>
      <header className="workspace-header">
        <Link className="workspace-wordmark" href="/" aria-label="ClipForge AI home"><span className="workspace-mark">C<span>·</span></span>CLIPFORGE <span>AI</span></Link>
        <Link className="workspace-back" href="/">Back to the story <span aria-hidden="true">↗</span></Link>
      </header>

      <section className="account-bar" aria-label="Signed-in account"><div><span className="panel-kicker">SIGNED IN</span><strong>{account.email}</strong><span>{teams.map((team) => `${team.name} · ${team.role}`).join("  /  ")}</span></div><div><button type="button" onClick={() => setPasswordChangeOpen((value) => !value)}>Change password</button><button type="button" onClick={() => void signOut()}>Sign out</button></div>
        {passwordChangeOpen && <form className="password-change" onSubmit={(event) => void changePassword(event)}><label>Current password<input name="current-password" type="password" autoComplete="current-password" required /></label><label>New password<input name="new-password" type="password" autoComplete="new-password" minLength={12} maxLength={128} required /></label><button type="submit">Update password</button></form>}
      </section>

      {teams.map((team) => <section className="team-panel" key={team.id} aria-label={`${team.name} access`}>
        <div className="team-panel-heading"><div><p className="panel-kicker">WORKSPACE ACCESS</p><strong>{team.name}</strong><span>Your role: {team.role}</span></div></div>
        {team.role === "owner" && <form className="team-invite-form" onSubmit={(event) => void createInvitation(event, team)}><label>Invite by email<input type="email" value={inviteEmail} onChange={(event) => setInviteEmail(event.target.value)} maxLength={320} required placeholder="colleague@example.com" /></label><label>Role<select value={inviteRole} onChange={(event) => setInviteRole(event.target.value as "editor" | "reviewer")}><option value="reviewer">Reviewer · view only</option><option value="editor">Editor · edit and render</option></select></label><button type="submit">Create 24-hour invitation</button></form>}
        {inviteUrl && team.role === "owner" && <div className="invite-link"><label>Share this one-time invite link<input readOnly value={inviteUrl} onFocus={(event) => event.currentTarget.select()} /></label><button type="button" onClick={() => void navigator.clipboard?.writeText(inviteUrl)}>Copy link</button></div>}
        {inviteError && <p role="alert" className="workspace-error">{inviteError}</p>}
        <ul className="team-member-list">{(teamMembers[team.id] ?? []).map((member) => <li key={member.membership_id}><span>{member.email}</span><span>{member.role}</span>{team.role === "owner" && member.role !== "owner" && <button type="button" onClick={() => void removeMember(team, member)}>Remove</button>}</li>)}</ul>
        <p className="team-local-note">Invitations are copied manually. Invite links grant access to this workspace and expire after 24 hours.</p>
      </section>)}
      <form className="create-team-form" onSubmit={(event) => void createTeam(event)}><label>New workspace<input value={newTeamName} onChange={(event) => setNewTeamName(event.target.value)} maxLength={120} required placeholder="Workspace name" /></label><button type="submit">Create workspace</button>{teamCreateError && <p role="alert">{teamCreateError}</p>}</form>

      <section className="workspace-intro">
        <p className="workspace-eyebrow"><span /> MILESTONE 06 · PRIVATE TEAM WORKSPACES</p>
        <h1>Shape the<br /><em>moment.</em></h1>
        <p className="workspace-lede">Transcribe a permitted video, review and edit transcript-aligned moments, then render a private portrait draft for preview and download.</p>
        <div className="workspace-policy">
          <span className="policy-icon" aria-hidden="true">i</span>
          <div><strong>Local development only</strong><span>{config ? `${config.accepted_formats.map((format) => format.toUpperCase()).join(" / ")} · ${formatBytes(config.max_upload_bytes)} max per source · ${formatBytes(config.max_media_storage_bytes)} total local quota · ${Math.round(config.max_video_duration_seconds / 60)} min max · deleted after ${config.source_retention_days} days` : "Loading current upload limits…"}</span></div>
        </div>
        <p className="youtube-note">You can save a YouTube link as a project reference. Video processing still requires an authorized MP4 or MOV upload.</p>
        <p className="model-note">The first transcription downloads the selected speech model into local storage. Your uploaded video and transcript stay on this machine.</p>
      </section>

      <section className="workspace-content" aria-labelledby="projects-heading">
        <div className="projects-heading"><div><p className="workspace-eyebrow"><span /> YOUR WORKSPACE</p><h2 id="projects-heading">Projects <span>{projects.length.toString().padStart(2, "0")}</span></h2></div><span className="local-badge"><i /> LOCAL</span></div>

        {teams.some((team) => team.role !== "reviewer") && <form className="create-project" onSubmit={createProject}>
          <label className="sr-only" htmlFor="project-name">Project name</label>
          <input id="project-name" name="project-name" autoComplete="off" maxLength={120} placeholder="Name a new project…" value={projectName} onChange={(event) => setProjectName(event.target.value)} required />
          {teams.filter((team) => team.role !== "reviewer").length > 1 && <label className="sr-only" htmlFor="project-team">Workspace</label>}
          {teams.filter((team) => team.role !== "reviewer").length > 1 && <select id="project-team" value={selectedTeamId} onChange={(event) => setSelectedTeamId(event.target.value)} aria-label="Project workspace">{teams.filter((team) => team.role !== "reviewer").map((team) => <option key={team.id} value={team.id}>{team.name}</option>)}</select>}
          <button type="submit" disabled={busyId === "create" || !projectName.trim()}>{busyId === "create" ? "Creating…" : "New project"}<span aria-hidden="true">↗</span></button>
        </form>}

        {message && <p className="workspace-message" role="status">{message}</p>}
        {error && <p className="workspace-error" role="alert">{error}</p>}

        <div className="project-list" aria-live="polite">
          {projects.length === 0 && <div className="empty-projects"><span aria-hidden="true">✳</span><strong>Your next story starts here.</strong><p>Create a project to make room for a source video.</p></div>}
          {projects.map((project, index) => {
            const source = project.sources[0];
            const latestJob = [...(project.transcription_jobs ?? [])].sort(
              (left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime(),
            )[0];
            const latestRun = [...(project.candidate_runs ?? [])]
              .filter((run) => run.transcription_job_id === latestJob?.id)
              .sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime())[0];
            const projectRole = teams.find((team) => team.id === project.team_id)?.role ?? "reviewer";
            const canEdit = projectRole === "owner" || projectRole === "editor";
            const isOwner = projectRole === "owner";
            return (
              <article className="project-card" key={project.id}>
                <div className="project-card-head"><span className="project-number">{(index + 1).toString().padStart(2, "0")}</span><div className="project-name"><h3>{project.name}</h3><span>Created {new Date(project.created_at).toLocaleDateString()} · {projectRole}</span></div>{isOwner && <button className="delete-project" type="button" onClick={() => void removeProject(project)} disabled={busyId === project.id} aria-label={`Delete ${project.name} project`}>Delete project</button>}</div>
                {project.youtube_url && <div className="youtube-reference"><span>YOUTUBE REFERENCE</span><a href={project.youtube_url} target="_blank" rel="noreferrer">{project.youtube_url}</a>{isOwner && <button type="button" onClick={() => void removeYouTubeReference(project)} disabled={busyId === project.id}>Remove link</button>}<p>This link is stored for reference only. ClipForge does not fetch YouTube video bytes; upload a permitted video file to transcribe it.</p></div>}
                {source ? (
                  <>
                    <div className="source-file"><div className="source-file-icon" aria-hidden="true">▧</div><div className="source-file-details"><strong>{source.original_filename}</strong><span>{source.media_format.toUpperCase()} · {formatBytes(source.size_bytes)} · {formatDuration(source.duration_seconds)}</span><span>Auto-delete {new Date(source.expires_at).toLocaleString()}</span></div><span className="source-ready">SOURCE ADDED</span>{isOwner && <button className="delete-source" type="button" onClick={() => void removeSource(project)} disabled={busyId === project.id} aria-label={`Delete source from ${project.name}`}>×</button>}</div>
                    <div className="transcription-panel">
                      <div className="transcription-panel-head">
                        <div><p className="panel-kicker">SPEECH TO TEXT</p><strong>{latestJob ? JOB_STAGE_LABELS[latestJob.stage] ?? latestJob.stage : "Create a timestamped transcript"}</strong></div>
                        {latestJob && <span className={`job-status job-status-${latestJob.status}`}>{latestJob.status.replaceAll("_", " ").toUpperCase()}</span>}
                      </div>
                      {latestJob?.detected_language && <p className="job-meta">Detected language: {latestJob.detected_language}{latestJob.language_probability !== null ? ` · ${Math.round(latestJob.language_probability * 100)}% model probability` : ""}</p>}
                      {latestJob?.failure_message && <p className="job-failure" role="alert">{latestJob.failure_message}</p>}
                      {latestJob?.progress_percent !== null && latestJob?.progress_percent !== undefined && <div className="job-progress" aria-label={`${latestJob.progress_percent}% complete`}><span style={{ width: `${latestJob.progress_percent}%` }} /></div>}
                      <div className="transcription-actions">
                        {canEdit && (!latestJob || ["complete", "cancelled"].includes(latestJob.status) || (latestJob.status === "failed" && !latestJob.retryable)) ? (
                          <button type="button" onClick={() => void startTranscription(project)} disabled={busyId === project.id}>{busyId === project.id ? "Starting…" : latestJob ? "Transcribe again" : "Start transcription"}<span aria-hidden="true">↗</span></button>
                        ) : null}
                        {canEdit && latestJob?.retryable && <button type="button" onClick={() => void retryTranscription(project, latestJob)} disabled={busyId === project.id}>{busyId === project.id ? "Retrying…" : "Retry transcription"}<span aria-hidden="true">↗</span></button>}
                        {latestJob?.status === "complete" && <button className="transcript-view-button" type="button" onClick={() => void toggleTranscript(latestJob)}>{expandedTranscriptId === latestJob.id ? "Hide transcript" : "View transcript"}</button>}
                        {canEdit && latestJob && ACTIVE_JOB_STATUSES.has(latestJob.status) && <button className="transcript-cancel-button" type="button" onClick={() => void cancelTranscription(project, latestJob)} disabled={busyId === project.id}>Cancel</button>}
                      </div>
                      {latestJob && expandedTranscriptId === latestJob.id && <div className="transcript-segments" aria-live="polite">{transcripts[latestJob.id]?.length ? transcripts[latestJob.id].map((segment) => <p key={segment.id}><time>{formatTimestamp(segment.start_ms)}–{formatTimestamp(segment.end_ms)}</time><span>{segment.text}</span></p>) : <p className="transcript-loading">Loading transcript…</p>}</div>}
                    </div>
                    {latestJob?.status === "complete" && <section className="candidate-panel" aria-label={`Highlight candidates for ${project.name}`}>
                      <div className="candidate-panel-heading"><div><p className="panel-kicker">MILESTONE 03 · REVIEWABLE MOMENTS</p><strong>Find candidate windows</strong></div><span className="candidate-count">{latestRun ? latestRun.candidates.length.toString().padStart(2, "0") : "—"}</span></div>
                      <p className="candidate-explainer">Choose a duration range and how many windows to review. These are transcript-aligned, chronological suggestions—not quality scores or virality predictions.</p>
                      {canEdit && <form className="candidate-options" onSubmit={(event) => void createCandidateRun(event, project, latestJob)}>
                        <label>Minimum seconds<input name="min-duration" type="number" min="1" max="3600" step="1" required /></label>
                        <label>Maximum seconds<input name="max-duration" type="number" min="1" max="3600" step="1" required /></label>
                        <label>Max windows<input name="candidate-limit" type="number" min="1" max="100" step="1" required /></label>
                        <button type="submit" disabled={busyId === project.id}>{busyId === project.id ? "Finding windows…" : "Find moments"}<span aria-hidden="true">↗</span></button>
                      </form>}
                      {latestRun && <div className="candidate-run-results">
                        <p className="candidate-run-meta">{latestRun.total_candidates} eligible windows · {latestRun.min_duration_seconds}–{latestRun.max_duration_seconds}s · sorted by source time{latestRun.sampled_evenly ? ` · ${latestRun.candidates.length} sampled evenly across the source` : ""}</p>
                        <ol className="candidate-list">
                          {latestRun.candidates.map((candidate) => <li className="candidate-card" key={candidate.id}>
                            <div className="candidate-card-top"><span>WINDOW {candidate.ordinal.toString().padStart(2, "0")}</span><time>{formatTimestamp(candidate.start_ms)}–{formatTimestamp(candidate.end_ms)}</time><span className={`candidate-status candidate-status-${candidate.status}`}>{candidate.status.toUpperCase()}</span></div>
                            <p className="candidate-quote">“{candidate.transcript_excerpt}”</p>
                            <ul className="candidate-signals">{candidate.signals.map((signal) => <li key={signal}>{signal}</li>)}</ul>
                            {latestRun && <CreatorEditor projectId={project.id} transcriptionJobId={latestRun.transcription_job_id} sourceDuration={source.duration_seconds} candidate={candidate} readOnly={!canEdit} onSaved={loadWorkspace} />}
                            {canEdit && <div className="candidate-review-actions"><button type="button" onClick={() => void updateCandidateStatus(project, candidate, "selected")} disabled={busyId === project.id || candidate.status === "selected"}>Select</button><button type="button" onClick={() => void updateCandidateStatus(project, candidate, "rejected")} disabled={busyId === project.id || candidate.status === "rejected"}>Reject</button></div>}
                            <div className="render-panel"><p className="panel-kicker">MILESTONE 04 · LOCAL DRAFT EXPORT</p><p>9:16 · 720 × 1280 · MP4 · full frame fit with blurred background · captions burned in</p>
                              {canEdit && <button type="button" onClick={() => void renderCandidate(project, candidate)} disabled={busyId === project.id || !["selected", "edited"].includes(candidate.status) || candidate.render_jobs?.some((render) => ACTIVE_RENDER_STATUSES.has(render.status))}>Render selected clip</button>}
                              {candidate.render_jobs?.map((render) => <div className="render-result" key={render.id}>
                                <strong>{render.status === "complete" ? "Draft ready" : render.status === "failed" ? "Render failed" : render.status.replaceAll("_", " ")}</strong>
                                {render.progress_percent !== null && ACTIVE_RENDER_STATUSES.has(render.status) && <div className="job-progress" aria-label={`${render.progress_percent}% complete`}><span style={{ width: `${render.progress_percent}%` }} /></div>}
                                {render.failure_message && <p className="job-failure" role="alert">{render.failure_message}</p>}
                                {render.status === "complete" && render.download_url && <><video controls preload="metadata" src={`${API}${render.download_url}`} aria-label={`Preview of ${candidate.title}`} /><p>{render.duration_ms ? `${(render.duration_ms / 1000).toFixed(1)} seconds` : ""} · {render.output_size_bytes ? formatBytes(render.output_size_bytes) : ""}</p><a href={`${API}${render.download_url}`} download>Download MP4</a>{render.captions_url && <> · <a href={`${API}${render.captions_url}`} download>Download SRT captions</a></>}</>}
                                {canEdit && ACTIVE_RENDER_STATUSES.has(render.status) && <button type="button" onClick={() => void cancelRender(project, render)} disabled={busyId === project.id}>Cancel render</button>}
                                {canEdit && render.retryable && <button type="button" onClick={() => void retryRender(project, render)} disabled={busyId === project.id}>Retry render</button>}
                              </div>)}
                            </div>
                          </li>)}
                        </ol>
                      </div>}
                    </section>}
                  </>
                ) : (
                  <>
                  {!project.youtube_url && <form className="youtube-reference-form" onSubmit={(event) => void saveYouTubeReference(event, project)}>
                    <label>YouTube video URL<input name="youtube-url" type="url" placeholder="https://www.youtube.com/watch?v=…" maxLength={2048} required disabled={busyId === project.id} /></label>
                    <label className="rights-check"><input type="checkbox" name="youtube-rights" required /><span>I own this video or have permission to use it in this project.</span></label>
                    <button type="submit" disabled={busyId === project.id}>{busyId === project.id ? "Saving link…" : "Save link reference"}<span aria-hidden="true">↗</span></button>
                    <p>Saving a link does not import or transcribe the video. Processing needs an authorized video file upload.</p>
                  </form>}
                  <form className="source-upload" onSubmit={(event) => void uploadSource(event, project)}>
                    <label className="file-picker">{busyId === project.id ? "Uploading and validating…" : "Choose an MP4 or MOV video"}<input name="video" type="file" accept=".mp4,.mov,video/mp4,video/quicktime" required disabled={busyId === project.id} /></label>
                    <label className="rights-check"><input type="checkbox" name="rights_confirmed" required /><span>I own this video or have permission to process it.</span></label>
                    <button type="submit" disabled={busyId === project.id}>{busyId === project.id ? "Please wait…" : "Upload source"}<span aria-hidden="true">↗</span></button>
                  </form>
                  </>
                )}
              </article>
            );
          })}
        </div>
      </section>

      <footer className="workspace-footer"><span>ClipForge AI <i>·</i> Local source + transcription</span><span>Your source and transcript stay on this machine.</span></footer>
    </main>
  );
}

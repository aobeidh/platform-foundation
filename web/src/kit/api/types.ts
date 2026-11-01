// Shapes of the platform API, as served by platform-kernel 0.3 and the exemplar service.
// The conformance test replays a journey captured from the real service and checks the simulated provider
// returns the same keys, so these types and both providers stay in step.

export interface FieldProblem { pointer: string; code: string; message: string }

/** RFC 9457 problem details with the platform's catalogue code and correlation id. */
export interface Problem {
  type: string; title: string; status: number; code: string; detail: string;
  instance?: string; correlationId?: string; errors: FieldProblem[];
}

export interface Check { name: string; ok: boolean; detail: string }

export type VersionStatus = 'draft' | 'tested' | 'submitted' | 'returned' | 'active' | 'superseded' | 'retired' | 'discarded';
export type Approval = 'auto' | 'single' | 'maker_checker';
export type RecordStatus = 'draft' | 'active' | 'paused' | 'retired';

export interface VersionView<S = Record<string, unknown>> {
  version: number; status: VersionStatus; spec: S;
  createdBy: string; submittedBy: string | null; approvedBy: string | null;
  testResult: Check[] | null; editedBy: string[]; makerChecker: boolean; createdAt: string;
  testedBy: string | null; testedAt: string | null; reason: string | null;
}

export interface GovernedRecord<S = Record<string, unknown>> {
  id: string; kind: string; tenant: string | null; status: RecordStatus; revision: number;
  currentVersion: number; activeVersion: number | null; createdAt: string; updatedAt: string;
  current: VersionView<S>; active: VersionView<S> | null;
}

export interface VersionSummary<S = Record<string, unknown>> {
  version: number; status: VersionStatus; spec: S; createdBy: string; submittedBy: string | null; approvedBy: string | null;
}

export interface Page<T> { items: T[]; total: number }

export interface Capability { name: string; display: Record<string, string> }

export interface Me {
  subject: string; kind: string; tenant: string | null; platformScope: boolean; roles: string[];
  onBehalfOf: string | null; capabilities: Capability[]; service: string; simulated: string[];
}

export interface JsonSchema {
  type?: string | string[]; title?: string; description?: string; properties?: Record<string, JsonSchema>;
  required?: string[]; enum?: unknown[]; default?: unknown; minLength?: number; maxLength?: number;
  minimum?: number; maximum?: number; format?: string; additionalProperties?: boolean | JsonSchema;
  items?: JsonSchema; examples?: unknown[];
}

export interface KindInfo {
  kind: string; plural: string; display: Record<string, string>; makerChecker: 'always' | 'never' | 'policy';
  approval: Approval; requireTest: boolean;
  schema: JsonSchema; capabilities: { read: string; write: string; approve: string }; tests: string[];
}

export interface Transition {
  name: 'test' | 'submit' | 'approve' | 'reject' | 'pause' | 'resume' | 'retire' | 'discard';
  from?: VersionStatus[]; record?: RecordStatus[]; to: string; capability: 'write' | 'approve'; reason?: boolean;
}

export interface Kinds { items: KindInfo[]; lifecycle: { versionStates: VersionStatus[]; recordStates: RecordStatus[]; transitions: Transition[] } }

export interface PluginInfo {
  kind: string; id: string; version: string; spi: string; capabilities: string[];
  display: Record<string, string>; publisher: string; configSchema: JsonSchema; secrets: string[];
}

export interface Plugins extends Page<PluginInfo> {
  /** False when the caller may not configure: schemas and secret names are then withheld. */
  detail: boolean;
}

export type OperationStatus = 'pending' | 'running' | 'stalled' | 'succeeded' | 'failed' | 'cancelled';

export interface Operation {
  id: string; kind: string; status: OperationStatus; progress: number; result: Record<string, unknown> | null;
  error: { code: string; detail: string } | null; cancelRequested: boolean; createdBy: string; createdAt: string; updatedAt: string;
}

// Exemplar (connections service) ------------------------------------------------------------------------------

export interface ConnectionSpec { name: string; connector: string; connector_version: string; config: Record<string, unknown> }
export type Connection = GovernedRecord<ConnectionSpec>;
export interface Activation { connectionId: string; version: number; tenant: string | null; activatedAt: string; eventId: string }

import {
  caseAgentApi,
  caseRubricApi,
  editorHandoffApi,
  type AgentDraft,
  type EditorHandoffResult,
} from "../api/r6";

async function r6AgentContract(caseId: string, videoId: string) {
  const drafts = await caseAgentApi.drafts(caseId, { limit: 30 });
  const draft: AgentDraft | undefined = drafts.items[0];
  if (draft) await caseAgentApi.adoptDraft(caseId, draft.id, { title: draft.title, publish_content: draft.script });

  await caseAgentApi.generateScript(caseId, {
    brief: "生成一版带案例记忆的脚本。",
    memory_ids: [],
    persona_mode: "hard_ad",
    operation: "generate",
    variation_count: 1,
  });
  const rubric = await caseRubricApi.rubric(caseId);
  const calibration = await caseRubricApi.calibration(caseId);
  const proposal = await caseRubricApi.bumpProposal(caseId);
  const predictions = await caseRubricApi.predictions(caseId, { limit: 20 });
  const pendingRetro = await caseRubricApi.pendingRetro(caseId);
  (rubric.dimensions ?? []) satisfies unknown[];
  calibration.sample_size satisfies number;
  (predictions.items ?? []) satisfies unknown[];
  (pendingRetro.items ?? []) satisfies unknown[];
  if (proposal) {
    await caseRubricApi.acceptBump(caseId, proposal.id);
    await caseRubricApi.rejectBump(caseId, proposal.id, { reason: "R6 reject" });
  }
  const handoff: EditorHandoffResult = await editorHandoffApi.createEditorHandoff(videoId, { format: "zip" });
  await editorHandoffApi.createJianyingDraft(videoId, { template_id: "jianying_default" });
  handoff.package_artifact.uri satisfies string;
}

void r6AgentContract("case_demo", "finished_video_demo");

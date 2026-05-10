import type { ComputedRef, Ref } from "vue";
import { del as deleteRequest, patch as patchRequest, post } from "../api/client";
import { endpoints } from "../api/endpoints";

type ToastTone = "success" | "warning" | "error" | "info";

type ChecklistTemplateSourceType = "template" | "csv_import";
type ChecklistTemplateEditorMode = "create" | "edit" | "csv_readonly";

type ChecklistTemplateOptionLike = {
  uid: string;
  name: string;
  source_type: ChecklistTemplateSourceType;
};

type ChecklistColumnRawLike = {
  column_uid?: string | null;
  column_name?: string | null;
  display_order?: number | null;
  column_type?: string | null;
  column_editable?: boolean | null;
  is_removable?: boolean | null;
  system_key?: string | null;
  background_color?: string | null;
  text_color?: string | null;
};

type ChecklistTemplateDraftColumnLike = {
  column_uid: string;
  column_name: string;
  display_order: number;
  column_type: string;
  column_editable: boolean;
  is_removable: boolean;
  system_key?: string | null;
  background_color?: string | null;
  text_color?: string | null;
};

type TemplateRecordLike = {
  uid?: string | null;
  template_name?: string | null;
  description?: string | null;
  columns?: unknown;
};

type ChecklistRecordLike = {
  uid?: string | null;
  name?: string | null;
  description?: string | null;
  columns?: unknown;
};

interface UseChecklistTemplateCrudOptions<TDraftColumn extends ChecklistTemplateDraftColumnLike> {
  buildTimestampTag: () => string;
  loadWorkspace: () => Promise<void>;
  pushToast: (message: string, tone: ToastTone) => void;
  handleApiError: (error: unknown, fallbackMessage: string) => void;
  confirmDelete: (message: string) => boolean;
  defaultSourceIdentity: string;
  checklistTemplateOptions: ComputedRef<ChecklistTemplateOptionLike[]>;
  selectedChecklistTemplateEditorOption: ComputedRef<ChecklistTemplateOptionLike | null>;
  checklistTemplateEditorMode: Ref<ChecklistTemplateEditorMode>;
  checklistTemplateEditorHydrating: Ref<boolean>;
  checklistTemplateEditorSelectionUid: Ref<string>;
  checklistTemplateEditorSelectionSourceType: Ref<ChecklistTemplateSourceType | "">;
  checklistTemplateDraftTemplateUid: Ref<string>;
  checklistTemplateDraftName: Ref<string>;
  checklistTemplateDraftDescription: Ref<string>;
  checklistTemplateDraftColumns: Ref<TDraftColumn[]>;
  checklistTemplateEditorDirty: Ref<boolean>;
  checklistTemplateEditorSaving: Ref<boolean>;
  checklistTemplateSelectionUid: Ref<string>;
  checklistTemplateDeleteBusyByUid: Ref<Record<string, boolean>>;
  templateRecords: Ref<TemplateRecordLike[]>;
  checklistRecords: Ref<ChecklistRecordLike[]>;
  selectedChecklistUid: Ref<string>;
  checklistDetailUid: Ref<string>;
  canSaveChecklistTemplateDraft: ComputedRef<boolean>;
  canSaveChecklistTemplateDraftAsNew: ComputedRef<boolean>;
  canCloneChecklistTemplateDraft: ComputedRef<boolean>;
  canArchiveChecklistTemplateDraft: ComputedRef<boolean>;
  canConvertChecklistTemplateDraft: ComputedRef<boolean>;
  canDeleteChecklistTemplateDraft: ComputedRef<boolean>;
  normalizeChecklistTemplateDraftColumns: (
    columns: Array<ChecklistColumnRawLike | TDraftColumn>,
    options?: { ensureTaskColumn?: boolean }
  ) => TDraftColumn[];
  createBlankChecklistTemplateDraftColumns: () => TDraftColumn[];
  validateChecklistTemplateDraftPayload: (
    templateName: string,
    columns: TDraftColumn[]
  ) => string | null;
  toChecklistTemplateColumnPayload: (columns: TDraftColumn[]) => Array<Record<string, unknown>>;
}

const toArray = <T>(value: unknown): T[] => (Array.isArray(value) ? (value as T[]) : []);

export const useChecklistTemplateCrud = <TDraftColumn extends ChecklistTemplateDraftColumnLike>(
  options: UseChecklistTemplateCrudOptions<TDraftColumn>
) => {
  const buildChecklistTemplateDraftName = (): string => `Template ${options.buildTimestampTag().slice(-6)}`;

  const applyChecklistTemplateEditorDraft = (payload: {
    selectionUid: string;
    selectionSourceType: ChecklistTemplateSourceType | "";
    mode: ChecklistTemplateEditorMode;
    templateUid: string;
    templateName: string;
    description: string;
    columns: Array<ChecklistColumnRawLike | TDraftColumn>;
    ensureTaskColumn?: boolean;
  }) => {
    options.checklistTemplateEditorHydrating.value = true;
    options.checklistTemplateEditorSelectionUid.value = payload.selectionUid;
    options.checklistTemplateEditorSelectionSourceType.value = payload.selectionSourceType;
    options.checklistTemplateEditorMode.value = payload.mode;
    options.checklistTemplateDraftTemplateUid.value = payload.templateUid;
    options.checklistTemplateDraftName.value = payload.templateName.trim() || buildChecklistTemplateDraftName();
    options.checklistTemplateDraftDescription.value = payload.description;
    options.checklistTemplateDraftColumns.value = options.normalizeChecklistTemplateDraftColumns(payload.columns, {
      ensureTaskColumn: payload.ensureTaskColumn ?? payload.mode !== "csv_readonly"
    });
    options.checklistTemplateEditorDirty.value = false;
    options.checklistTemplateEditorHydrating.value = false;
  };

  const startNewChecklistTemplateDraft = () => {
    applyChecklistTemplateEditorDraft({
      selectionUid: "",
      selectionSourceType: "",
      mode: "create",
      templateUid: "",
      templateName: buildChecklistTemplateDraftName(),
      description: "",
      columns: options.createBlankChecklistTemplateDraftColumns(),
      ensureTaskColumn: true
    });
  };

  const selectChecklistTemplateForEditor = (templateUid: string, sourceType: ChecklistTemplateSourceType) => {
    const uid = String(templateUid ?? "").trim();
    if (!uid) {
      return;
    }
    const selectedOption =
      options.checklistTemplateOptions.value.find((entry) => entry.uid === uid && entry.source_type === sourceType) ?? null;
    if (!selectedOption) {
      return;
    }
    options.checklistTemplateSelectionUid.value = selectedOption.uid;
    if (selectedOption.source_type === "template") {
      const templateRecord =
        options.templateRecords.value.find((entry) => String(entry.uid ?? "").trim() === selectedOption.uid) ?? null;
      if (!templateRecord) {
        options.pushToast("Selected template is unavailable", "warning");
        return;
      }
      applyChecklistTemplateEditorDraft({
        selectionUid: selectedOption.uid,
        selectionSourceType: selectedOption.source_type,
        mode: "edit",
        templateUid: selectedOption.uid,
        templateName: String(templateRecord.template_name ?? selectedOption.name),
        description: String(templateRecord.description ?? ""),
        columns: toArray<ChecklistColumnRawLike>(templateRecord.columns),
        ensureTaskColumn: true
      });
      return;
    }
    const checklistRecord =
      options.checklistRecords.value.find((entry) => String(entry.uid ?? "").trim() === selectedOption.uid) ?? null;
    if (!checklistRecord) {
      options.pushToast("Selected CSV entry is unavailable", "warning");
      return;
    }
    applyChecklistTemplateEditorDraft({
      selectionUid: selectedOption.uid,
      selectionSourceType: selectedOption.source_type,
      mode: "csv_readonly",
      templateUid: "",
      templateName: String(checklistRecord.name ?? selectedOption.name),
      description: String(checklistRecord.description ?? ""),
      columns: toArray<ChecklistColumnRawLike>(checklistRecord.columns),
      ensureTaskColumn: false
    });
  };

  const syncChecklistTemplateEditorSelection = (preferredUid = "", preferredType: ChecklistTemplateSourceType | "" = "") => {
    const availableOptions = options.checklistTemplateOptions.value;
    if (!availableOptions.length) {
      startNewChecklistTemplateDraft();
      return;
    }
    const preferredOption =
      (preferredUid && preferredType
        ? availableOptions.find((entry) => entry.uid === preferredUid && entry.source_type === preferredType)
        : null) ?? null;
    if (preferredOption) {
      selectChecklistTemplateForEditor(preferredOption.uid, preferredOption.source_type);
      return;
    }
    const selectedOption = options.selectedChecklistTemplateEditorOption.value;
    if (selectedOption) {
      if (options.checklistTemplateEditorMode.value !== "create") {
        selectChecklistTemplateForEditor(selectedOption.uid, selectedOption.source_type);
      }
      return;
    }
    selectChecklistTemplateForEditor(availableOptions[0].uid, availableOptions[0].source_type);
  };

  const buildChecklistTemplateDraftPayload = () => {
    const templateName = options.checklistTemplateDraftName.value.trim();
    const validationError = options.validateChecklistTemplateDraftPayload(
      templateName,
      options.checklistTemplateDraftColumns.value
    );
    if (validationError) {
      throw new Error(validationError);
    }
    return {
      template_name: templateName,
      description: options.checklistTemplateDraftDescription.value.trim(),
      columns: options.toChecklistTemplateColumnPayload(options.checklistTemplateDraftColumns.value)
    };
  };

  const saveChecklistTemplateDraft = async () => {
    if (!options.canSaveChecklistTemplateDraft.value) {
      return;
    }
    const templateUid = options.checklistTemplateDraftTemplateUid.value.trim();
    if (!templateUid) {
      return;
    }
    options.checklistTemplateEditorSaving.value = true;
    try {
      const payload = buildChecklistTemplateDraftPayload();
      await patchRequest(`${endpoints.checklistTemplates}/${templateUid}`, { patch: payload });
      await options.loadWorkspace();
      syncChecklistTemplateEditorSelection(templateUid, "template");
      options.pushToast("Template saved", "success");
    } catch (error) {
      options.handleApiError(error, "Unable to save template");
    } finally {
      options.checklistTemplateEditorSaving.value = false;
    }
  };

  const saveChecklistTemplateDraftAsNew = async () => {
    if (!options.canSaveChecklistTemplateDraftAsNew.value) {
      return;
    }
    options.checklistTemplateEditorSaving.value = true;
    try {
      const payload = buildChecklistTemplateDraftPayload();
      const created = await post<{ uid?: string | null }>(endpoints.checklistTemplates, {
        template: {
          ...payload,
          created_by_team_member_rns_identity: options.defaultSourceIdentity
        }
      });
      await options.loadWorkspace();
      const createdUid = String(created.uid ?? "").trim();
      if (createdUid) {
        syncChecklistTemplateEditorSelection(createdUid, "template");
      } else {
        syncChecklistTemplateEditorSelection();
      }
      options.pushToast("Template created", "success");
    } catch (error) {
      options.handleApiError(error, "Unable to create template");
    } finally {
      options.checklistTemplateEditorSaving.value = false;
    }
  };

  const cloneChecklistTemplateDraft = async () => {
    if (!options.canCloneChecklistTemplateDraft.value) {
      return;
    }
    const templateUid = options.checklistTemplateDraftTemplateUid.value.trim();
    if (!templateUid) {
      return;
    }
    options.checklistTemplateEditorSaving.value = true;
    try {
      const baseName = options.checklistTemplateDraftName.value.trim() || "Template";
      const cloned = await post<{ uid?: string | null }>(`${endpoints.checklistTemplates}/${templateUid}/clone`, {
        template_name: `${baseName} Copy ${options.buildTimestampTag().slice(-4)}`,
        description: options.checklistTemplateDraftDescription.value.trim(),
        created_by_team_member_rns_identity: options.defaultSourceIdentity
      });
      await options.loadWorkspace();
      const clonedUid = String(cloned.uid ?? "").trim();
      if (clonedUid) {
        syncChecklistTemplateEditorSelection(clonedUid, "template");
      } else {
        syncChecklistTemplateEditorSelection();
      }
      options.pushToast("Template cloned", "success");
    } catch (error) {
      options.handleApiError(error, "Unable to clone template");
    } finally {
      options.checklistTemplateEditorSaving.value = false;
    }
  };

  const archiveChecklistTemplateDraft = async () => {
    if (!options.canArchiveChecklistTemplateDraft.value) {
      return;
    }
    const templateUid = options.checklistTemplateDraftTemplateUid.value.trim();
    if (!templateUid) {
      return;
    }
    const templateName = options.checklistTemplateDraftName.value.trim() || "Template";
    if (/\[ARCHIVED\]/i.test(templateName)) {
      options.pushToast("Template already archived", "info");
      return;
    }
    options.checklistTemplateEditorSaving.value = true;
    try {
      await patchRequest(`${endpoints.checklistTemplates}/${templateUid}`, {
        patch: {
          template_name: `${templateName} [ARCHIVED]`
        }
      });
      await options.loadWorkspace();
      syncChecklistTemplateEditorSelection(templateUid, "template");
      options.pushToast("Template archived", "success");
    } catch (error) {
      options.handleApiError(error, "Unable to archive template");
    } finally {
      options.checklistTemplateEditorSaving.value = false;
    }
  };

  const convertChecklistTemplateDraftToServerTemplate = async () => {
    if (!options.canConvertChecklistTemplateDraft.value) {
      return;
    }
    options.checklistTemplateEditorSaving.value = true;
    try {
      const payload = buildChecklistTemplateDraftPayload();
      const created = await post<{ uid?: string | null }>(endpoints.checklistTemplates, {
        template: {
          ...payload,
          created_by_team_member_rns_identity: options.defaultSourceIdentity
        }
      });
      await options.loadWorkspace();
      const createdUid = String(created.uid ?? "").trim();
      if (createdUid) {
        syncChecklistTemplateEditorSelection(createdUid, "template");
      } else {
        syncChecklistTemplateEditorSelection();
      }
      options.pushToast("CSV template converted", "success");
    } catch (error) {
      options.handleApiError(error, "Unable to convert CSV template");
    } finally {
      options.checklistTemplateEditorSaving.value = false;
    }
  };

  const isChecklistTemplateDeleteBusy = (templateUid: string): boolean => {
    const uid = String(templateUid ?? "").trim();
    if (!uid) {
      return false;
    }
    return Boolean(options.checklistTemplateDeleteBusyByUid.value[uid]);
  };

  const deleteChecklistTemplateFromCard = async (
    templateUid: string,
    sourceType: ChecklistTemplateSourceType,
    templateName: string
  ): Promise<boolean> => {
    const uid = String(templateUid ?? "").trim();
    if (!uid || isChecklistTemplateDeleteBusy(uid)) {
      return false;
    }
    const name = String(templateName ?? uid).trim() || uid;
    const targetLabel = sourceType === "template" ? "template" : "CSV import template";
    if (!options.confirmDelete(`Delete ${targetLabel} "${name}"?`)) {
      return false;
    }
    options.checklistTemplateDeleteBusyByUid.value = {
      ...options.checklistTemplateDeleteBusyByUid.value,
      [uid]: true
    };
    try {
      if (sourceType === "template") {
        await deleteRequest(`${endpoints.checklistTemplates}/${uid}`);
      } else {
        await deleteRequest(`${endpoints.checklists}/${uid}`);
        if (options.selectedChecklistUid.value === uid) {
          options.selectedChecklistUid.value = "";
        }
        if (options.checklistDetailUid.value === uid) {
          options.checklistDetailUid.value = "";
        }
      }
      if (options.checklistTemplateSelectionUid.value === uid) {
        options.checklistTemplateSelectionUid.value = "";
      }
      await options.loadWorkspace();
      options.pushToast(sourceType === "template" ? "Template deleted" : "CSV import template deleted", "success");
      return true;
    } catch (error) {
      options.handleApiError(
        error,
        sourceType === "template" ? "Unable to delete template" : "Unable to delete CSV import template"
      );
      return false;
    } finally {
      const nextBusy = { ...options.checklistTemplateDeleteBusyByUid.value };
      delete nextBusy[uid];
      options.checklistTemplateDeleteBusyByUid.value = nextBusy;
    }
  };

  const deleteChecklistTemplateDraft = async () => {
    if (!options.canDeleteChecklistTemplateDraft.value) {
      return;
    }
    const selectedOption = options.selectedChecklistTemplateEditorOption.value;
    if (!selectedOption) {
      return;
    }
    const removed = await deleteChecklistTemplateFromCard(
      selectedOption.uid,
      selectedOption.source_type,
      selectedOption.name
    );
    if (!removed) {
      return;
    }
    syncChecklistTemplateEditorSelection();
  };

  return {
    startNewChecklistTemplateDraft,
    selectChecklistTemplateForEditor,
    syncChecklistTemplateEditorSelection,
    saveChecklistTemplateDraft,
    saveChecklistTemplateDraftAsNew,
    cloneChecklistTemplateDraft,
    archiveChecklistTemplateDraft,
    convertChecklistTemplateDraftToServerTemplate,
    deleteChecklistTemplateDraft
  };
};

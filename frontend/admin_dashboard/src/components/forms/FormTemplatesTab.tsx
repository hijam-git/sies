import { useCallback, useEffect, useState } from 'react';
import { apiClient } from '../../lib/api';
import type { FormBlock, FormTemplate } from '../../lib/api';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText, apiFieldErrors } from '../../lib/apiErrors';
import Field, { FieldGrid, FormError } from '../common/Field';
import ResponsiveTable from '../common/ResponsiveTable';
import type { Column } from '../common/ResponsiveTable';
import { btnPrimary, btnSecondary, inputCls, selectCls } from '../common/styles';
import BlockEditor from './BlockEditor';
import { blockIndexInError } from './blockTypes';
import { mergePrintDocuments } from './printDocument';

/**
 * Settings → Form templates (`docs/07` §9).
 *
 * A list, and a block editor with an A4 preview beside it. The preview is the
 * point: an administrator editing the pledge wording has to see the sheet the
 * guardian will sign, and every madrasah's form differs enough that describing
 * the change in words does not do it (§2).
 *
 * **The preview is rendered by the server**, from `/form-templates/<id>/preview/`,
 * so what it shows is the same code that produces the printed page. It follows
 * the SAVED template — there is no endpoint that renders unsaved blocks — so
 * Save is what refreshes it, and the pane says so rather than pretending to be
 * live.
 */

function TemplatePreview({ templateId, refreshToken }: { templateId: number; refreshToken: number }) {
  const { t } = useT();
  const [html, setHtml] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Deferred by a tick rather than run in the effect body: the fetch's own
  // state writes would otherwise cascade a render before the first paint. The
  // shape every list screen in this project uses.
  useEffect(() => {
    let alive = true;
    const timer = setTimeout(() => {
      setError(null);
      void apiClient
        .templatePreviewHtml(templateId, 'blank')
        .then((doc) => {
          if (alive) setHtml(mergePrintDocuments([doc]));
        })
        .catch((err: unknown) => {
          if (alive) setError(apiErrorText(err, t, t('Could not produce this form.')));
        });
    }, 0);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [templateId, refreshToken, t]);

  if (error) return <FormError message={error} />;
  if (!html) return <p className="py-8 text-center text-sm text-gray-500">{t('Loading...')}</p>;

  return (
    <div className="overflow-auto rounded-lg border border-gray-200 bg-gray-100" style={{ touchAction: 'pinch-zoom' }}>
      {/* Scaled to a third so a whole A4 sheet is legible beside the editor at
          laptop width; the container scrolls rather than the page (§7a rule 1). */}
      <div style={{ width: 'calc(210mm * 0.42)', height: 1180 * 0.42 }}>
        <div
          style={{
            width: '210mm',
            height: 1180,
            transform: 'scale(0.42)',
            transformOrigin: 'top left',
          }}
        >
          <iframe
            title={t('Form preview')}
            srcDoc={html}
            className="block border-0 bg-white"
            style={{ width: '210mm', height: 1180 }}
          />
        </div>
      </div>
    </div>
  );
}

export default function FormTemplatesTab() {
  const { t } = useT();
  const { can } = usePermissions();
  const mayEdit = can('settings', 'update');

  const [templates, setTemplates] = useState<FormTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [editing, setEditing] = useState<FormTemplate | null>(null);
  const [blocks, setBlocks] = useState<FormBlock[]>([]);
  const [name, setName] = useState('');
  const [nameBn, setNameBn] = useState('');
  const [paper, setPaper] = useState('A4');
  const [margins, setMargins] = useState('12mm 14mm');

  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [blockErrors, setBlockErrors] = useState<Record<number, string>>({});
  const [previewToken, setPreviewToken] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      setTemplates(await apiClient.listAll<FormTemplate>('/form-templates/', '?ordering=name'));
    } catch (err) {
      setLoadError(apiErrorText(err, t, t('Could not load the form templates.')));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
  }, [load]);

  const openEditor = (template: FormTemplate) => {
    setEditing(template);
    setBlocks(template.blocks ?? []);
    setName(template.name);
    setNameBn(template.name_bn);
    setPaper(template.paper);
    setMargins(template.margins);
    setFormError(null);
    setBlockErrors({});
    setSaved(false);
  };

  const save = async () => {
    if (!editing) return;
    setSaving(true);
    setSaved(false);
    setFormError(null);
    setBlockErrors({});
    try {
      const updated = await apiClient.patch<FormTemplate>('/form-templates/', editing.id, {
        name: name.trim(),
        name_bn: nameBn.trim(),
        blocks,
        paper,
        margins: margins.trim(),
      });
      setEditing(updated);
      setBlocks(updated.blocks ?? []);
      setSaved(true);
      // The preview follows the saved template, so this is the moment it is
      // worth re-rendering — and the only moment it changes.
      setPreviewToken((x) => x + 1);
      await load();
    } catch (err) {
      const fields = apiFieldErrors(err);
      // The backend names the offending block — `blocks[3] (prose) …` — so the
      // message goes on THAT block. A generic toast for a thirteen-block form
      // leaves the administrator hunting for their own typo.
      const blocksError = fields.blocks;
      const index = blocksError ? blockIndexInError(blocksError) : null;
      if (blocksError && index !== null) {
        setBlockErrors({ [index]: blocksError });
        setFormError(t('One block was rejected. It is marked below.'));
      } else {
        setFormError(
          blocksError ?? apiErrorText(err, t, t('Could not save this form template.')),
        );
      }
    } finally {
      setSaving(false);
    }
  };

  const duplicate = async (template: FormTemplate) => {
    setFormError(null);
    try {
      await apiClient.create<FormTemplate>('/form-templates/', {
        name: `${template.name} (copy)`,
        name_bn: template.name_bn ? `${template.name_bn} (কপি)` : '',
        form_type: template.form_type,
        blocks: template.blocks,
        paper: template.paper,
        margins: template.margins,
        // Never a second default: the database allows one per type per
        // institution, and a copy is a draft until somebody says otherwise.
        is_default: false,
        is_active: template.is_active,
      });
      await load();
    } catch (err) {
      setFormError(apiErrorText(err, t, t('Could not copy this form template.')));
    }
  };

  const makeDefault = async (template: FormTemplate) => {
    setFormError(null);
    try {
      // The old default is cleared FIRST. One default per type is a database
      // constraint, so setting the new one first is an IntegrityError rather
      // than a race.
      const current = templates.find(
        (x) => x.is_default && x.form_type === template.form_type && x.id !== template.id,
      );
      if (current) await apiClient.patch<FormTemplate>('/form-templates/', current.id, { is_default: false });
      await apiClient.patch<FormTemplate>('/form-templates/', template.id, { is_default: true });
      await load();
    } catch (err) {
      setFormError(apiErrorText(err, t, t('Could not set the default form.')));
    }
  };

  const columns: Column<FormTemplate>[] = [
    {
      key: 'name',
      label: t('Template'),
      primary: true,
      render: (x) => (
        <span className="block">
          <span className="block">{x.name_bn || x.name}</span>
          <span className="block text-xs text-gray-500">{x.name}</span>
        </span>
      ),
    },
    { key: 'type', label: t('Type'), render: (x) => x.form_type },
    { key: 'blocks', label: t('Blocks'), render: (x) => (x.blocks ?? []).length },
    {
      key: 'default',
      label: t('Default'),
      render: (x) =>
        x.is_default ? (
          <span className="inline-flex rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800">
            {t('Default')}
          </span>
        ) : (
          '—'
        ),
    },
    {
      key: 'actions',
      label: t('Actions'),
      action: true,
      cellClass: 'px-4 py-3 text-right',
      headClass: 'px-4 py-3 text-right',
      render: (x) => (
        <span className="inline-flex flex-wrap justify-end gap-2">
          <button type="button" onClick={() => openEditor(x)} className={btnSecondary}>
            {mayEdit ? t('Edit blocks') : t('View blocks')}
          </button>
          {mayEdit && (
            <button type="button" onClick={() => void duplicate(x)} className={btnSecondary}>
              {t('Duplicate')}
            </button>
          )}
          {mayEdit && !x.is_default && (
            <button type="button" onClick={() => void makeDefault(x)} className={btnSecondary}>
              {t('Make default')}
            </button>
          )}
        </span>
      ),
    },
  ];

  if (editing) {
    return (
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-gray-900">
              {editing.name_bn || editing.name}
            </h2>
          </div>
          <button type="button" onClick={() => setEditing(null)} className={btnSecondary}>
            {t('Back to the list')}
          </button>
        </div>

        {saved && (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
            {t('Saved successfully!')}
          </div>
        )}
        <FormError message={formError} />

        {/* One column on a phone, editor and preview side by side from lg —
            the preview is a reference, so it goes UNDER the editor on a narrow
            screen rather than squeezing both. */}
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          <div className="space-y-4">
            <FieldGrid>
              <Field label={t('Name (English)')}>
                <input
                  value={name}
                  disabled={!mayEdit}
                  onChange={(e) => setName(e.target.value)}
                  className={inputCls}
                />
              </Field>
              <Field label={t('Name (Bangla)')}>
                <input
                  value={nameBn}
                  disabled={!mayEdit}
                  onChange={(e) => setNameBn(e.target.value)}
                  className={inputCls}
                />
              </Field>
              <Field label={t('Paper')}>
                <select
                  value={paper}
                  disabled={!mayEdit}
                  onChange={(e) => setPaper(e.target.value)}
                  className={selectCls}
                >
                  <option value="A4">A4</option>
                  <option value="Legal">Legal</option>
                </select>
              </Field>
              <Field label={t('Margins')} hint="12mm 14mm">
                <input
                  value={margins}
                  disabled={!mayEdit}
                  onChange={(e) => setMargins(e.target.value)}
                  className={inputCls}
                />
              </Field>
            </FieldGrid>

            <BlockEditor
              blocks={blocks}
              onChange={setBlocks}
              placeholders={editing.placeholder_groups ?? {}}
              blockErrors={blockErrors}
              disabled={!mayEdit}
            />

            {mayEdit && (
              <button
                type="button"
                onClick={() => void save()}
                disabled={saving}
                className={`${btnPrimary} w-full sm:w-auto`}
              >
                {saving ? t('Saving…') : t('Save and refresh the preview')}
              </button>
            )}
          </div>

          <div className="space-y-2">
            <p className="text-xs text-gray-500">
              {t('The preview shows the saved template, rendered by the server — blank, the way the stack is printed.')}
            </p>
            <TemplatePreview templateId={editing.id} refreshToken={previewToken} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-500">
        {t('The printed forms this institution issues. Editing the pledge text here changes what prints — no developer, no deploy.')}
      </p>

      <FormError message={loadError ?? formError} />

      <ResponsiveTable
        columns={columns}
        rows={templates}
        rowKey={(x) => x.id}
        empty={loading ? t('Loading…') : t('No form templates yet.')}
      />
    </div>
  );
}

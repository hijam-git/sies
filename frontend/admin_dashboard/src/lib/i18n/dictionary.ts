/**
 * Bangla translations, merged from per-section files so that two people
 * editing two modules do not edit the same file.
 *
 * Keys are the English source strings, exactly as they appear in `t('…')`.
 * That is why a typo in a component reads as "the Bangla did not apply"
 * rather than as an error — the fallback is the key itself.
 */
import common from './dict/common';
import nav from './dict/nav';
import auth from './dict/auth';
import dashboard from './dict/dashboard';
import errors from './dict/errors';
import admin from './dict/admin';
import students from './dict/students';
import staff from './dict/staff';
import academics from './dict/academics';
import fees from './dict/fees';
import finance from './dict/finance';
import attendance from './dict/attendance';
import exams from './dict/exams';
import forms from './dict/forms';
import reports from './dict/reports';

export const BN: Record<string, string> = {
  ...common,
  ...nav,
  ...auth,
  ...dashboard,
  ...errors,
  ...admin,
  ...students,
  ...staff,
  ...academics,
  ...attendance,
  ...exams,
  ...forms,
  ...reports,
  ...fees,
  ...finance,
};

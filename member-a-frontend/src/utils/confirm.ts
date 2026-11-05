import { ElMessageBox } from 'element-plus';
export async function confirmDisable(name: string) {
  try {
    await ElMessageBox.confirm(
      `停用“${name}”会影响后续使用，历史学习记录仍会保留。确认继续？`,
      '确认停用',
      { confirmButtonText: '确认停用', cancelButtonText: '取消' },
    );
    return true;
  } catch {
    return false;
  }
}

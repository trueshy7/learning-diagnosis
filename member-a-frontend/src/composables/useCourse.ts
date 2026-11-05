import { useLoad } from './useLoad';
import { api } from '../api/services';
export function useCourse() {
  return useLoad(
    () => 'current-course',
    async () => {
      const courses = await api.courses();
      if (!courses[0]) throw new Error('当前没有课程，请联系后端管理员初始化');
      return courses[0];
    },
  );
}

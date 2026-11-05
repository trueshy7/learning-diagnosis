const part = encodeURIComponent;
export const endpoints = {
  login: '/auth/login',
  me: '/auth/me',
  logout: '/auth/logout',
  courses: '/courses',
  course: (id: string) => `/courses/${part(id)}`,
  attempts: '/attempts',
  attempt: (id: string) => `/attempts/${part(id)}`,
  submit: (id: string) => `/attempts/${part(id)}/submit`,
  result: (id: string) => `/attempts/${part(id)}/result`,
  task: (id: string) => `/tasks/${part(id)}`,
  retry: (id: string) => `/tasks/${part(id)}/retry`,
  reports: '/reports',
  report: (id: string) => `/reports/${part(id)}`,
  recommendations: (id: string) => `/reports/${part(id)}/recommendations`,
  comparison: (id: string) => `/reports/${part(id)}/comparison`,
  resource: (id: string) => `/resources/${part(id)}`,
  file: (id: string) => `/resources/${part(id)}/file`,
  teacher: (entity: string, id?: string) =>
    `/teacher/${entity}${id ? `/${part(id)}` : ''}`,
  teacherReport: (uid: string, rid: string) =>
    `/teacher/students/${part(uid)}/reports/${part(rid)}`,
};

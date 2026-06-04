import axios from 'axios'
import { ElMessage } from 'element-plus'

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8001/api/v1',
  timeout: 15_000,
})

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const detail = error.response?.data?.detail
    ElMessage.error(typeof detail === 'string' ? detail : '请求失败，请检查后端服务')
    return Promise.reject(error)
  },
)

export default apiClient

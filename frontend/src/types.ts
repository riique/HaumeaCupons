export type Product = {
  id: number | string
  keywords: string[]
  max_price: number
  active?: boolean
  created_by?: string
  created_at?: string
}

export type ProductPayload = Omit<Product, 'id'>

export type ChatGroups = string | string[]

export type Finding = {
  id: number | string
  timestamp: string
  product_keyword: string
  url: string
  price_found: number | null
  price_ok: boolean
  source_group: string
  coupons: string[]
  links: string[]
  source_chat_id?: string
  source_message_id?: string
  user_id?: string
}

export type ApiState = {
  products: Product[]
  chat_groups: ChatGroups
  findings: Finding[]
}

export type FindingsPage = {
  findings: Finding[]
  limit: number
  offset: number
}

export type Tab = 'overview' | 'products' | 'groups' | 'findings'

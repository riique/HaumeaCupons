export type Product = {
  id: number
  keyword: string
  min_price: number
  max_price: number
}

export type ProductPayload = Omit<Product, 'id'>

export type ChatGroups = string | string[]

export type Finding = {
  id: number
  timestamp: string
  product_keyword: string
  url: string
  price_found: number | null
  price_ok: boolean
  source_group: string
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

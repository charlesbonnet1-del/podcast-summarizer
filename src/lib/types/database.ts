export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export interface Database {
  public: {
    Tables: {
      users: {
        Row: {
          id: string
          email: string
          telegram_chat_id: number | null
          connection_code: string | null
          default_duration: number
          voice_id: string
          rss_token: string
          subscription_status: 'free' | 'pro'
          created_at: string
          updated_at: string
        }
        Insert: {
          id: string
          email: string
          telegram_chat_id?: number | null
          connection_code?: string | null
          default_duration?: number
          voice_id?: string
          rss_token?: string
          subscription_status?: 'free' | 'pro'
          created_at?: string
          updated_at?: string
        }
        Update: {
          id?: string
          email?: string
          telegram_chat_id?: number | null
          connection_code?: string | null
          default_duration?: number
          voice_id?: string
          rss_token?: string
          subscription_status?: 'free' | 'pro'
          created_at?: string
          updated_at?: string
        }
      }
      content_queue: {
        Row: {
          id: string
          user_id: string
          url: string
          title: string | null
          source_type: 'youtube' | 'article' | 'podcast'
          status: 'pending' | 'processing' | 'processed' | 'failed'
          error_message: string | null
          processed_content: string | null
          created_at: string
          updated_at: string
        }
        Insert: {
          id?: string
          user_id: string
          url: string
          title?: string | null
          source_type: 'youtube' | 'article' | 'podcast'
          status?: 'pending' | 'processing' | 'processed' | 'failed'
          error_message?: string | null
          processed_content?: string | null
          created_at?: string
          updated_at?: string
        }
        Update: {
          id?: string
          user_id?: string
          url?: string
          title?: string | null
          source_type?: 'youtube' | 'article' | 'podcast'
          status?: 'pending' | 'processing' | 'processed' | 'failed'
          error_message?: string | null
          processed_content?: string | null
          created_at?: string
          updated_at?: string
        }
      }
      episodes: {
        Row: {
          id: string
          user_id: string
          title: string
          summary_text: string | null
          audio_url: string
          audio_duration: number | null
          sources: Json
          created_at: string
        }
        Insert: {
          id?: string
          user_id: string
          title: string
          summary_text?: string | null
          audio_url: string
          audio_duration?: number | null
          sources?: Json
          created_at?: string
        }
        Update: {
          id?: string
          user_id?: string
          title?: string
          summary_text?: string | null
          audio_url?: string
          audio_duration?: number | null
          sources?: Json
          created_at?: string
        }
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      generate_connection_code: {
        Args: Record<PropertyKey, never>
        Returns: string
      }
    }
    Enums: {
      [_ in never]: never
    }
  }
}

export type User = Database['public']['Tables']['users']['Row']
export type ContentQueue = Database['public']['Tables']['content_queue']['Row']
export type Episode = Database['public']['Tables']['episodes']['Row']

export interface UserInterest {
  id: string
  user_id: string
  keyword: string
  created_at: string
}

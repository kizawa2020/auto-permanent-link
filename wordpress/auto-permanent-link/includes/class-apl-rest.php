<?php
/**
 * REST ハンドラ: 投稿画面からの slug 推奨リクエストを受け、
 *  - nonce 検証（wp_rest）
 *  - edit_post 権限チェック
 * を行ってから Lambda(/suggest) へプロキシする。
 *
 * サーバー間呼び出しなので (A) X-Api-Secret と (B) x-api-key をここで付与する。
 * シークレット/APIキーはブラウザには一切出さない（PHP から送るだけ）。
 *
 * ルート: POST /wp-json/auto-permanent-link/v1/suggest
 *   body: { post_id: int, title: string, excerpt?: string }
 *   resp: { suggestions: [ { slug, length }, ... ] }
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class APL_Rest {

	private static $instance = null;

	public static function instance() {
		if ( null === self::$instance ) {
			self::$instance = new self();
		}
		return self::$instance;
	}

	private function __construct() {
		add_action( 'rest_api_init', array( $this, 'register_routes' ) );
	}

	public function register_routes() {
		register_rest_route(
			'auto-permanent-link/v1',
			'/suggest',
			array(
				'methods'             => 'POST',
				'callback'            => array( $this, 'handle_suggest' ),
				'permission_callback' => array( $this, 'check_permission' ),
				'args'                => array(
					'post_id' => array( 'required' => true, 'type' => 'integer' ),
					'title'   => array( 'required' => true, 'type' => 'string' ),
					'excerpt' => array( 'required' => false, 'type' => 'string' ),
					'exclude' => array( 'required' => false, 'type' => 'array' ),
					'variety' => array( 'required' => false, 'type' => 'boolean' ),
				),
			)
		);
	}

	/**
	 * nonce は WP REST 標準の X-WP-Nonce(wp_rest) で検証される。
	 * 表示条件と揃え、管理者・編集者(edit_others_posts)のみ実行を許可する。
	 * 寄稿者・投稿者は自分の投稿を編集できても、この機能は使わせない。
	 */
	public function check_permission( WP_REST_Request $request ) {
		return current_user_can( 'edit_others_posts' );
	}

	public function handle_suggest( WP_REST_Request $request ) {
		$endpoint = get_option( APL_OPT_ENDPOINT, '' );
		$secret   = get_option( APL_OPT_SHARED_SECRET, '' );
		$api_key  = get_option( APL_OPT_API_KEY, '' );

		if ( empty( $endpoint ) || empty( $secret ) ) {
			return new WP_Error(
				'apl_not_configured',
				'Auto Permanent Link is not configured. Set the API endpoint and shared secret in Settings.',
				array( 'status' => 500 )
			);
		}

		$title   = trim( (string) $request->get_param( 'title' ) );
		$excerpt = trim( (string) $request->get_param( 'excerpt' ) );
		if ( '' === $title ) {
			return new WP_Error( 'apl_no_title', 'Title is required.', array( 'status' => 400 ) );
		}

		$url  = rtrim( $endpoint, '/' ) . '/suggest';
		$body = array( 'title' => $title );
		if ( '' !== $excerpt ) {
			$body['excerpt'] = $excerpt;
		}

		// 「もう一度生成」用: 既出候補(exclude)と多様性フラグ(variety)を転送。
		$exclude_raw = $request->get_param( 'exclude' );
		if ( is_array( $exclude_raw ) && ! empty( $exclude_raw ) ) {
			$exclude = array();
			foreach ( $exclude_raw as $s ) {
				$s = sanitize_title( (string) $s );
				if ( '' !== $s ) {
					$exclude[] = $s;
				}
			}
			$exclude = array_slice( array_values( array_unique( $exclude ) ), 0, 50 );
			if ( ! empty( $exclude ) ) {
				$body['exclude'] = $exclude;
			}
		}
		if ( $request->get_param( 'variety' ) ) {
			$body['variety'] = true;
		}

		$headers = array(
			'Content-Type' => 'application/json',
			'X-Api-Secret' => $secret, // (A)
		);
		if ( ! empty( $api_key ) ) {
			$headers['x-api-key'] = $api_key; // (B)
		}

		$response = wp_remote_post(
			$url,
			array(
				'headers' => $headers,
				'body'    => wp_json_encode( $body ),
				'timeout' => 30,
			)
		);

		if ( is_wp_error( $response ) ) {
			return new WP_Error(
				'apl_upstream_error',
				'Failed to reach the slug service: ' . $response->get_error_message(),
				array( 'status' => 502 )
			);
		}

		$code = wp_remote_retrieve_response_code( $response );
		$raw  = wp_remote_retrieve_body( $response );

		if ( 200 !== (int) $code ) {
			return new WP_Error(
				'apl_upstream_status',
				'Slug service returned status ' . $code,
				array( 'status' => 502 )
			);
		}

		$data = json_decode( $raw, true );
		if ( ! is_array( $data ) || ! isset( $data['suggestions'] ) ) {
			return new WP_Error(
				'apl_bad_response',
				'Unexpected response from slug service.',
				array( 'status' => 502 )
			);
		}

		return rest_ensure_response( $data );
	}
}

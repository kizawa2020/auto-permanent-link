/* Auto Permanent Link — 投稿画面メタボックスのフロント処理。
 *
 * 流れ:
 *  1. 「候補を生成」押下 → 現在のタイトル(＋任意で本文冒頭)を取得
 *  2. REST /auto-permanent-link/v1/suggest を X-WP-Nonce 付きで POST
 *  3. 返ってきた候補をカード表示
 *  4. 「適用」で WordPress の slug 入力欄へ反映（Classic / Gutenberg 両対応）
 */
( function () {
	'use strict';

	var cfg = window.APL_CONFIG || {};

	// これまで提示した slug を累積（同一タイトルでの「もう一度」用の除外リスト）。
	var shownSlugs = [];
	var lastTitle = null;

	function $( id ) {
		return document.getElementById( id );
	}

	function esc( s ) {
		var d = document.createElement( 'div' );
		d.textContent = String( s == null ? '' : s );
		return d.innerHTML;
	}

	// タイトル取得（Classic: #title / Gutenberg: editor store）
	function getTitle() {
		var el = $( 'title' );
		if ( el && el.value ) {
			return el.value;
		}
		if ( window.wp && wp.data && wp.data.select( 'core/editor' ) ) {
			return wp.data.select( 'core/editor' ).getEditedPostAttribute( 'title' ) || '';
		}
		return '';
	}

	// 本文冒頭取得（プレーンテキスト先頭 300 文字程度）
	function getExcerpt() {
		var text = '';
		if ( window.wp && wp.data && wp.data.select( 'core/editor' ) ) {
			text = wp.data.select( 'core/editor' ).getEditedPostAttribute( 'content' ) || '';
		} else {
			// Classic: TinyMCE か textarea#content
			if ( window.tinymce && tinymce.get( 'content' ) && ! tinymce.get( 'content' ).isHidden() ) {
				text = tinymce.get( 'content' ).getContent( { format: 'text' } );
			} else {
				var ta = $( 'content' );
				text = ta ? ta.value : '';
			}
		}
		// タグ除去して詰める
		var tmp = document.createElement( 'div' );
		tmp.innerHTML = text;
		var plain = ( tmp.textContent || tmp.innerText || '' ).replace( /\s+/g, ' ' ).trim();
		return plain.slice( 0, 300 );
	}

	function getPostId() {
		var el = $( 'post_ID' );
		if ( el && el.value ) {
			return parseInt( el.value, 10 ) || 0;
		}
		if ( window.wp && wp.data && wp.data.select( 'core/editor' ) ) {
			return wp.data.select( 'core/editor' ).getCurrentPostId() || 0;
		}
		return 0;
	}

	// slug 反映（サーバー側確定方式）。
	// done({ applied, reason }) を返す。
	//
	// 確定した真因: Classic/Gutenberg いずれもコア JS が保存直前に #post_name を上書きするため、
	// フロントで #post_name / #new-post-slug に書く方式は必ず負ける（実測 SET value post_name "")。
	// 解決: フロントは隠しフィールド #apl_selected_slug に選択値を入れるだけにし、
	// 保存時にサーバー(wp_insert_post_data フック / class-apl-save.php)が post_name を強制する。
	// これによりコア JS の書き戻しと競合しない。表示プレビューは UX のため更新するが確定はサーバー。
	function applySlug( slug, done ) {
		done = done || function () {};

		var hidden = $( 'apl_selected_slug' );
		if ( ! hidden ) {
			done( { applied: false, reason: 'no-hidden-field' } );
			return;
		}
		hidden.value = slug;

		// 表示プレビューのみ更新（保存でサーバーが確定するため見た目の案内）。コアの編集欄や
		// #post_name には触れない（競合防止）。
		var sample = $( 'editable-post-name' );
		if ( sample ) {
			sample.textContent = slug;
		}
		var full = $( 'editable-post-name-full' );
		if ( full ) {
			full.textContent = slug;
		}

		done( { applied: true, reason: 'server-side' } );
	}

	function setStatus( msg, isError ) {
		var s = $( 'apl-status' );
		if ( ! s ) {
			return;
		}
		s.textContent = msg || '';
		s.className = 'apl-status' + ( isError ? ' apl-error' : '' );
	}

	function renderSuggestions( list ) {
		var ul = $( 'apl-suggestions' );
		ul.innerHTML = '';
		if ( ! list || ! list.length ) {
			setStatus( '候補が得られませんでした。', true );
			return;
		}
		list.forEach( function ( item ) {
			// 表示した候補を累積（次回「もう一度」で除外する）。
			if ( item && item.slug && shownSlugs.indexOf( item.slug ) === -1 ) {
				shownSlugs.push( item.slug );
			}
			var li = document.createElement( 'li' );
			li.className = 'apl-suggestion';
			li.innerHTML =
				'<code class="apl-slug">' + esc( item.slug ) + '</code>' +
				'<span class="apl-len">' + esc( item.length ) + '字</span>' +
				'<button type="button" class="button apl-apply">適用</button>';
			li.querySelector( '.apl-apply' ).addEventListener( 'click', function () {
				applySlug( item.slug, function ( res ) {
					if ( res.applied ) {
						setStatus( '「' + item.slug + '」を選択しました。投稿を更新/公開すると、この slug がパーマリンクに確定します。', false );
					} else {
						setStatus( 'slug を保存できませんでした。ページを再読み込みして再度お試しください。', true );
					}
				} );
			} );
			ul.appendChild( li );
		} );
	}

	function generate() {
		var btn = $( 'apl-generate' );
		var title = getTitle().trim();
		if ( ! title ) {
			setStatus( 'タイトルを入力してください。', true );
			return;
		}

		// タイトルが変わったら履歴をリセット（別記事の候補を除外しない）。
		if ( title !== lastTitle ) {
			shownSlugs = [];
			lastTitle = title;
		}

		var payload = { post_id: getPostId(), title: title };
		if ( $( 'apl-use-excerpt' ) && $( 'apl-use-excerpt' ).checked ) {
			var ex = getExcerpt();
			if ( ex ) {
				payload.excerpt = ex;
			}
		}
		// 2回目以降（既に候補を出している）は、別候補を要求する。
		if ( shownSlugs.length ) {
			payload.exclude = shownSlugs.slice( 0, 50 );
			payload.variety = true;
		}

		btn.disabled = true;
		setStatus( shownSlugs.length ? '別の候補を生成中…' : '生成中…' );

		fetch( cfg.restUrl, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'X-WP-Nonce': cfg.nonce,
			},
			body: JSON.stringify( payload ),
		} )
			.then( function ( res ) {
				return res.json().then( function ( body ) {
					return { ok: res.ok, body: body };
				} );
			} )
			.then( function ( r ) {
				if ( ! r.ok ) {
					var msg = r.body && r.body.message ? r.body.message : 'エラーが発生しました。';
					setStatus( msg, true );
					return;
				}
				setStatus( '' );
				renderSuggestions( r.body.suggestions );
			} )
			.catch( function () {
				setStatus( '通信エラーが発生しました。', true );
			} )
			.finally( function () {
				btn.disabled = false;
			} );
	}

	document.addEventListener( 'DOMContentLoaded', function () {
		var btn = $( 'apl-generate' );
		if ( btn ) {
			btn.addEventListener( 'click', generate );
		}
	} );
} )();

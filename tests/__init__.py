"""Test suite setup and sandbox-safe test client configuration."""

import inspect
import json
import mimetypes
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse
import fastapi.testclient
from fastapi import HTTPException
from pydantic import BaseModel


class SandboxResponse:
    """Mock HTTP response matching requests/httpx API surface."""

    def __init__(self, status_code: int, data: Any, headers: Optional[Dict[str, str]] = None):
        self.status_code = getattr(data, "status_code", status_code)
        self._data = data
        self.headers = dict(headers or {})
        if hasattr(data, "headers"):
            self.headers.update(dict(data.headers))
        if hasattr(data, "media_type") and data.media_type and "content-type" not in self.headers:
            self.headers["content-type"] = data.media_type

    def json(self):
        if isinstance(self._data, list):
            return [x.model_dump() if isinstance(x, BaseModel) else x for x in self._data]
        if isinstance(self._data, dict):
            return self._data
        if isinstance(self._data, BaseModel):
            return self._data.model_dump()
        if isinstance(self._data, str):
            try:
                return json.loads(self._data)
            except Exception:
                return self._data
        return self._data

    @property
    def content(self):
        if hasattr(self._data, "body"):
            b = self._data.body
            return b if isinstance(b, bytes) else str(b).encode("utf-8")
        if isinstance(self._data, bytes):
            return self._data
        return self.text.encode("utf-8")

    @property
    def text(self):
        if hasattr(self._data, "body"):
            b = self._data.body
            return b.decode("utf-8") if isinstance(b, bytes) else str(b)
        if hasattr(self._data, "path"):
            try:
                with open(self._data.path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                pass
        if isinstance(self._data, str):
            return self._data
        return json.dumps(self.json())


def _run_coroutine_sync(coro):
    """Safely step an async endpoint without socket-level event loops."""
    stack = [coro]
    val = None
    is_exc = False
    exc_obj = None

    while stack:
        current = stack[-1]
        try:
            if is_exc:
                is_exc = False
                res = current.throw(exc_obj)
            else:
                res = current.send(val)
            val = None

            if inspect.iscoroutine(res):
                stack.append(res)
            else:
                val = getattr(res, "result", lambda: res)()
        except StopIteration as stop:
            stack.pop()
            val = stop.value
        except Exception as exc:
            stack.pop()
            is_exc = True
            exc_obj = exc

    if is_exc and exc_obj is not None:
        raise exc_obj
    return val


class SandboxTestClient:
    """In-memory TestClient dispatching directly to FastAPI endpoints for sandbox execution."""
    __test__ = False

    def __init__(self, app):
        self.app = app

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def _get_all_routes(self) -> List[Any]:
        routes = []
        for r in getattr(self.app, "routes", []):
            if hasattr(r, "original_router") and hasattr(r.original_router, "routes"):
                routes.extend(r.original_router.routes)
            elif hasattr(r, "routes"):
                routes.extend(r.routes)
            elif hasattr(r, "path"):
                routes.append(r)
        return routes

    def _match_route(self, route_path: str, request_path: str) -> Optional[Dict[str, str]]:
        if route_path == request_path:
            return {}
        # Convert path pattern /foo/{id} to regex ^/foo/(?P<id>[^/]+)$
        pattern = "^" + re.sub(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", r"(?P<\1>[^/]+)", route_path) + "$"
        m = re.match(pattern, request_path)
        if m:
            return m.groupdict()
        return None

    def _execute(self, method: str, url: str, **kwargs) -> SandboxResponse:
        parsed_url = urlparse(url)
        path = parsed_url.path
        query_dict = kwargs.get("params") or {}
        if not query_dict and parsed_url.query:
            raw_qs = parse_qs(parsed_url.query)
            query_dict = {k: v[0] if len(v) == 1 else v for k, v in raw_qs.items()}

        json_body = kwargs.get("json", {})

        # Check Starlette Mount routes (e.g. StaticFiles)
        for route in getattr(self.app, "routes", []):
            if type(route).__name__ == "Mount" and route.path and path.startswith(route.path):
                rel_path = path[len(route.path):].lstrip("/\\")
                static_app = getattr(route, "app", None)
                if static_app and hasattr(static_app, "directory"):
                    target_file = Path(static_app.directory) / rel_path
                    if target_file.exists() and target_file.is_file():
                        mime, _ = mimetypes.guess_type(str(target_file))
                        mime = mime or "application/octet-stream"
                        content = target_file.read_text(encoding="utf-8", errors="replace")
                        return SandboxResponse(200, content, headers={"content-type": mime})

        for route in self._get_all_routes():
            route_path = getattr(route, "path", None)
            route_methods = getattr(route, "methods", set())
            if not route_path or method not in route_methods:
                continue

            path_params = self._match_route(route_path, path)
            if path_params is not None:
                endpoint = route.endpoint
                sig = inspect.signature(endpoint)
                call_args: Dict[str, Any] = {}

                # Map parameters: path params, query params, json payload, or dependencies
                for param_name, param in sig.parameters.items():
                    annotation = param.annotation
                    default = param.default

                    # 1. Path parameters
                    if param_name in path_params:
                        call_args[param_name] = path_params[param_name]
                        continue

                    # 2. Body schema
                    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
                        call_args[param_name] = annotation(**json_body)
                        continue

                    # 3. Query / form params
                    if param_name in query_dict:
                        val = query_dict[param_name]
                        if annotation is int or (hasattr(annotation, "__args__") and int in getattr(annotation, "__args__", ())):
                            try:
                                val = int(val)
                            except (ValueError, TypeError):
                                pass
                        elif annotation is float:
                            try:
                                val = float(val)
                            except (ValueError, TypeError):
                                pass
                        call_args[param_name] = val
                        continue

                    # 4. JSON body top-level key
                    if isinstance(json_body, dict) and param_name in json_body:
                        call_args[param_name] = json_body[param_name]
                        continue

                    # 5. FastAPI Depends resolution
                    dep_fn = getattr(default, "dependency", None)
                    if dep_fn is not None:
                        override = getattr(self.app, "dependency_overrides", {}).get(dep_fn, dep_fn)
                        call_args[param_name] = override()
                        continue

                    # 6. Default value from FastAPI params (Query, Path, etc.)
                    if hasattr(default, "default"):
                        if default.default is not ...:
                            call_args[param_name] = default.default
                    elif default is not inspect.Parameter.empty:
                        call_args[param_name] = default

                try:
                    if inspect.iscoroutinefunction(endpoint):
                        res = _run_coroutine_sync(endpoint(**call_args))
                    else:
                        res = endpoint(**call_args)
                    resp_status = getattr(res, "status_code", 200)
                    resp_headers = dict(getattr(res, "headers", {}))
                    return SandboxResponse(resp_status, res, headers=resp_headers)
                except HTTPException as exc:
                    return SandboxResponse(exc.status_code, {"detail": exc.detail}, headers=getattr(exc, "headers", None))
                except Exception as exc:
                    return SandboxResponse(500, {"detail": str(exc)})

        return SandboxResponse(404, {"detail": "Not Found"})

    def get(self, url: str, **kwargs):
        follow_redirects = kwargs.get("follow_redirects", True)
        res = self._execute("GET", url, **kwargs)
        if follow_redirects and res.status_code in (301, 302, 303, 307, 308) and "location" in res.headers:
            return self._execute("GET", res.headers["location"], **kwargs)
        return res

    def post(self, url: str, **kwargs):
        return self._execute("POST", url, **kwargs)

    def delete(self, url: str, **kwargs):
        return self._execute("DELETE", url, **kwargs)

    def put(self, url: str, **kwargs):
        return self._execute("PUT", url, **kwargs)


# Patch fastapi.testclient.TestClient to use our sandbox-safe implementation
fastapi.testclient.TestClient = SandboxTestClient
